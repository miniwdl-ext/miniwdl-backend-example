# miniwdl-backend-example

This example [container backend](https://miniwdl.readthedocs.io/en/latest/runner_backends.html) plugin for [miniwdl](https://github.com/chanzuckerberg/miniwdl) runs WDL task containers by simply shelling out to `docker run` &mdash; a toy version of miniwdl's default docker integration. This provides an illustrative starting point for third-party Python packages to integrate other container runtimes.

To run the example, cd into a clone of this repo and:

```bash
pip3 install .
export MINIWDL__SCHEDULER__CONTAINER_BACKEND=example_docker_run
miniwdl run_self_test
```

Installing the Python package registers a specific [entry point](https://packaging.python.org/en/latest/specifications/entry-points/) which miniwdl discovers upon starting (details in [setup.py](https://github.com/miniwdl-ext/miniwdl-backend-example/blob/main/setup.py)). Then we activate it by setting the environment variable `MINIWDL__SCHEDULER__CONTAINER_BACKEND` to the registered backend name `example_docker_run`. (Equivalently, we could set `[scheduler] container_backend = example_docker_run` in a [miniwdl configuration file](https://miniwdl.readthedocs.io/en/latest/runner_reference.html#configuration).)

### Implementation overview

The main goal is to provide an implementation of the [`TaskContainer` abstract base class](https://github.com/chanzuckerberg/miniwdl/blob/main/WDL/runtime/task_container.py). Each miniwdl task runner thread instantiates your subclass and synchronously invokes its methods to configure and run the container.

See [miniwdl_backend_example/docker_run.py](https://github.com/miniwdl-ext/miniwdl-backend-example/blob/main/miniwdl_backend_example/docker_run.py) for the annotated implementation, and [miniwdl-aws](https://github.com/miniwdl-ext/miniwdl-aws) for a production-ready example. The former "shells out" to a subprocess to run the container, while the latter makes AWS API calls to schedule a job and poll its status.

Besides the container scheduling, the other main design focus is mounting file inputs/outputs and the working directory. Miniwdl prefers to mount these *in situ* on the POSIX filesystem (possibly a network share) instead of copying/down/uploading them, based on a desired mapping of virtual in-container paths to host/network paths maintained by `TaskContainer`. Our subclass is responsible for configuring the container to effect this mapping. The container's standard output and error streams are also communicated via the filesystem.

When your plugin is ready, consider publishing it as [a PyPI package](https://github.com/miniwdl-ext/miniwdl-aws/blob/main/release.sh) and/or [a Docker image](https://github.com/miniwdl-ext/miniwdl-aws/blob/main/Dockerfile).
