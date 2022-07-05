import os
import psutil
import threading
import subprocess
import multiprocessing
from contextlib import ExitStack
import WDL
from WDL._util import StructuredLogMessage as _


class DockerRun(WDL.runtime.task_container.TaskContainer):
    """
    Subclasses miniwdl TaskContainer; each task runner thread instantiates this class to set up &
    execute a container.

    Refer to the base class:
      https://github.com/chanzuckerberg/miniwdl/blob/main/WDL/runtime/task_container.py
    """

    # To simplify this example we'll use a lock, shared by all instances of this class, to execute
    # docker containers one-at-a-time.
    _run_lock = threading.Lock()

    # Set by copy_input_files() below
    _copied_input_files: bool = False

    @classmethod
    def global_init(cls, cfg, logger):
        """
        Perform any necessary process-wide initialization of the container backend
        """
        cls._resource_limits = {
            "cpu": multiprocessing.cpu_count(),
            "mem_bytes": psutil.virtual_memory().total,
        }
        logger.info(
            _(
                "initialized miniwdl_backend_example DockerRun plugin",
                resource_limits=cls._resource_limits,
            )
        )

    @classmethod
    def detect_resource_limits(cls, cfg, logger):
        """
        Detect the maximum cpu and mem_bytes the backend can provision -for any one container-
        """
        return cls._resource_limits

    def __init__(self, cfg, run_id, host_dir):
        super().__init__(cfg, run_id, host_dir)

    def copy_input_files(self, logger):
        """
        Copy input files into the task working directory. Normally this doesn't occur as we're
        instead mounting input files in their original location; but the operator can configure
        miniwdl to do this ([task_runtime] copy_input_files). The base class handles the actual
        copying; we just need to remember it occurred when we set up our mounts (below).
        """
        super().copy_input_files(logger)
        self._copied_input_files = True

    def _run(self, logger, terminating, command):
        """
        Run task

        Note: retry logic may cause _run() to be invoked multiple times on the same object
        """
        try:
            # contextlib.ExitStack() is useful for numerous "finally" actions
            with ExitStack() as cleanup:

                # Formulate `docker run` invocation
                invocation = self.docker_run_invocation(command)

                # Acquire class-wide lock for running a container; a production implementation
                # might have resource scheduling logic or submit to some external queue.
                cleanup.enter_context(self._run_lock)

                # The poll_stderr context yields a helper function that we should invoke frequently
                # to forward the task's standard error to miniwdl's verbose log.
                poll_stderr = cleanup.enter_context(self.poll_stderr_context(logger))

                # The task running context updates miniwdl's status bar for running tasks; we
                # should enter it when our container actually starts (not while it's still in a
                # resource scheduling queue).
                cleanup.enter_context(self.task_running_context())

                # Store the stdout/stderr of `docker run` itself (not the task command running
                # inside the container, which we handle separately below) in the run directory.
                docker_run_log_filename = os.path.join(self.host_dir, "docker_run.log")
                docker_run_log = cleanup.enter_context(open(docker_run_log_filename, "wb"))

                # Start `docker run` subprocess
                logger.debug(_("docker run", invocation=invocation))
                proc = subprocess.Popen(
                    invocation, cwd=self.host_dir, stdout=docker_run_log, stderr=subprocess.STDOUT
                )
                logger.notice(_("docker run", pid=proc.pid, log=docker_run_log_filename))

                # Long-poll for completion
                exit_code = None
                while exit_code is None:
                    # The terminating() flag turns true when miniwdl has received SIGTERM/SIGINT.
                    # In this event we should gracefully abort our container.
                    if terminating():
                        proc.terminate()
                    try:
                        exit_code = proc.wait(1)
                    except subprocess.TimeoutExpired:
                        pass
                    # Frequently invoke poll_stderr()
                    poll_stderr()

                # Invoke poll_stderr() once more after container exit, to get any final logs.
                poll_stderr()

                # If we aborted due to terminating(), then raise WDL.runtime.Terminated().
                # In a production implementation that submits to some external queue, we should
                # also check for terminating() flag while sitting in the queue and cancel the job
                # promptly if triggered. In that case we can raise Terminated(quiet=true) to emit
                # less log noise during the abort sequence (for tasks that never really started).
                if terminating():
                    raise WDL.runtime.Terminated()

                # Return container exit status (which might or might not be zero)
                assert isinstance(exit_code, int)
                return exit_code
        except Exception as exn:
            if isinstance(exn, WDL.runtime.Terminated):
                raise

            # In the event of an error (other than Terminated or non-zero container exit status),
            # emit an informative log message and raise a WDL.Error.RuntimeError (or some subclass
            # thereof)
            logger.error(_("unexpected DockerRun error", exception=str(exn)))
            raise WDL.Error.RuntimeError(str(exn))

    def docker_run_invocation(self, command):
        """
        Formulate the `docker run` invocation based on
        - command text (given)
        - configuration options (self.cfg)
        - input & output files (self.input_file_map)
        - runtime{} values (self.runtime_values)
        """
        ans = [
            "docker",
            "run",
            # CWD inside the container
            "--workdir",
            os.path.join(self.container_dir, "work"),
            # Run as the invoking uid inside the container; this avoids the annoying problem of
            # files written inside the container being owned by root afterwards. But it's
            # incompatible with task commands that assume they're running as root (e.g. to install
            # packages at runtime). That's okay for this example -- it suffices for miniwdl's
            # self-test -- but miniwdl's production backends jump through some hoops to chown the
            # working directory after letting the command as root.
            "--user",
            str(os.getuid()),
        ]

        # Provision cpu/memory based on self.runtime_values, which is a postprocessed version of
        # the task's evaluated runtime{} section (in particular, runtime.memory turns into integers
        # memory_limit and memory_reservation, both in bytes).
        cpu = self.runtime_values.get("cpu", 0)
        if cpu > 0:
            ans += ["--cpus", str(cpu)]
        # memory_limit = backend should kill the container if memory usage exceeds this (bytes)
        memory_limit = self.runtime_values.get("memory_limit", 0)
        if memory_limit > 0:
            ans += ["--memory", str(memory_limit)]
        # self.runtime_values.get("memory_reservation", 0) should be used to guide resource
        # scheduling (not relevant in this example running one container at a time).

        # Example of loading a custom configuration option from the .cfg file or environment. Always
        # provide a default value for custom options (that aren't set in miniwdl's default.cfg).
        """
        if self.cfg.get_bool("docker_run", "read_only_root_filesystem", False):
            ans.append("--read-only")
        """

        # File/Directory I/O mounts
        # If the task takes a very large number of inputs, then we might worry about the command
        # line exceeding some system limit. Then we might need to explore an alternate
        # implementation strategy, such as mounting the entire host filesystem and populating
        # the working directory with symlinks to the input files (miniwdl-aws does this).
        for (host_path, container_path, writable) in self.prepare_mounts(command):
            assert ":" not in (container_path + host_path)
            vol = f"{host_path}:{container_path}"
            if not writable:
                vol += ":ro"
            ans += ["-v", vol]

        # Docker image tag
        image = self.runtime_values.get(
            "docker", self.cfg.get_dict("task_runtime", "defaults")["docker"]
        )
        ans.append(image)

        # Bootstrapping within the container: execute the given command in a login shell with
        # stdout and stderr redirected into log files.
        ans += [
            "/bin/bash",
            "-c",
            "bash -l ../command >> ../stdout.txt 2>> ../stderr.txt",
        ]
        return ans

    def prepare_mounts(self, command):
        """
        Prepare list of (host_path, container_path, writable) to be mounted in the container
        """

        def touch_mount_point(host_path: str) -> None:
            # Touch each mount point in the working directory that wouldn't already exist; this
            # just ensures they'll be owned by the invoking user:group
            assert host_path.startswith(self.host_dir + "/")
            if host_path.endswith("/"):  # Directory mount point
                os.makedirs(host_path, exist_ok=True)
            else:  # File mount point
                os.makedirs(os.path.dirname(host_path), exist_ok=True)
                with open(host_path, "x") as _:
                    pass

        mounts = []

        # Mount stdout, stderr, and working directory read/write.
        # stdout has to go into self.host_stdout_txt(), which is where the stdout() WDL function
        # will look for it if called; ditto for stderr. Also, poll_stderr() tails
        # self.host_stderr_txt()
        touch_mount_point(self.host_stdout_txt())
        mounts.append(
            (self.host_stdout_txt(), os.path.join(self.container_dir, "stdout.txt"), True)
        )
        touch_mount_point(self.host_stderr_txt())
        mounts.append(
            (self.host_stderr_txt(), os.path.join(self.container_dir, "stderr.txt"), True)
        )
        mounts.append((self.host_work_dir(), os.path.join(self.container_dir, "work"), True))

        # Write command in a read-only file
        with open(os.path.join(self.host_dir, "command"), "w") as outfile:
            outfile.write(command)
        mounts.append(
            (
                os.path.join(self.host_dir, "command"),
                os.path.join(self.container_dir, "command"),
                False,
            )
        )

        # Mount input Files & Directories read-only
        # - self.input_path_map will have been populated previously
        # - Directory paths end in /
        # - skip these if copy_input_files() was used, since the inputs are already present in the
        #   working directory
        if not self._copied_input_files:
            for host_path, container_path in self.input_path_map.items():
                assert (not container_path.endswith("/")) or os.path.isdir(host_path.rstrip("/"))
                host_mount_point = os.path.join(
                    self.host_dir, os.path.relpath(container_path.rstrip("/"), self.container_dir)
                )
                if not os.path.exists(host_mount_point):
                    touch_mount_point(
                        host_mount_point + ("/" if container_path.endswith("/") else "")
                    )
                mounts.append((host_path.rstrip("/"), container_path.rstrip("/"), False))

        return mounts
