# miniwdl-backend-example

This Python project is a miniwdl container backend plugin, which runs task containers by simply shelling out to `docker run` -- a toy version of miniwdl's default docker integration. It's a minimal starting point for implementing other, more-interesting container backends.

To run the example, cd into a clone of this repo and:

```
pip3 install .
MINIWDL__SCHEDULER__CONTAINER_BACKEND=example_docker_run miniwdl run_self_test
```

Installing the plugin registers a specific [entry point](https://packaging.python.org/en/latest/specifications/entry-points/) which miniwdl discovers upon starting (details in setup.py). Then we activate it by setting the environment variable `MINIWDL__SCHEDULER__CONTAINER_BACKEND` to the registered backend name `example_docker_run`. (Equivalently we could set `[scheduler] container_backend=example_docker_run` in a [miniwdl configuration file](https://miniwdl.readthedocs.io/en/latest/runner_reference.html#configuration).)

See miniwdl_backend_example/docker_run.py for the annotated implementation, and [miniwdl-aws](https://github.com/miniwdl-ext/miniwdl-aws) for a production-ready example.
