from setuptools import setup, find_packages

with open("README.md") as fp:
    long_description = fp.read()

setup(
    name="miniwdl-backend-example",
    version="v0.0.1",
    description="miniwdl container backend example",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Wid L. Hacker",
    python_requires=">=3.6",
    packages=find_packages(),
    install_requires=["miniwdl>=1.6.0"],
    # The following entry point is how miniwdl discovers the plugin once this package has been
    # installed locally by `pip3 install .`.
    # - example_docker_run is the name to be set in the [scheduler] container_backend configuration
    #   option (env MINIWDL__SCHEDULER__CONTAINER_BACKEND) to cause miniwdl to use the plugin.
    # - miniwdl_backend_example:DockerRun is the package:class (exported by __init__.py) that
    #   miniwdl will instantiate in order to create a task container -- the concrete implementation
    #   of the TaskContainer abstract base class.
    entry_points={
        "miniwdl.plugin.container_backend": [
            "example_docker_run = miniwdl_backend_example:DockerRun"
        ],
    },
)
