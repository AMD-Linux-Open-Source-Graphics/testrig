# testrig

This is a tool that was written to make running the component tests for ROCm InBox packages easier and more consistent in both running and extracting error information.


## Usage

Testrig has two basic commands: run and check

  * `check` will look for packages declared as required and attempt to install any missing packages
  * `run` runs the tests after running the same process as `check`

## Input Format

Testrig uses [TOML](https://toml.io/en/) for declaring rig information. The exact format should be considered unstable and likely to change between releases.

## Run Tests

Platform-specific tests like the ones for apt will only run on those systems. To exclude a set of tests from collection,
run:

`pytest tests/ --ignore tests/test_packagemanager_apt.py`
