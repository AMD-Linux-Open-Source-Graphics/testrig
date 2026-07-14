
============================================================
  testrig
============================================================

Description
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `testrig` cli tool were created to make unified setup and coordination
of hardware tests less difficult.

Testrig was designed and written for an effort to test the ROCm InBox packages
across multiple distros.

Testrig uses `toml <https://toml.io/en/>`_ to describe tests.

Input Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A rig file has a top-level ``name`` field and one section per supported distro
(for example ``[ubuntu]`` or ``[fedora]``). Each distro section supports the
following fields:

test_binary_path
    Directory containing the test entry points.

test_binaries
    Allowlist of entry point names to run. Each name is combined with
    ``test_binary_path`` to build an absolute path to the binary. Only the
    binaries listed here are executed.

test_package_name
    Package that must be installed in order to run the tests.

test_debug_package_names
    Packages providing debug symbols, used when gathering debug information on
    failed tests.

extra_env_var
    Optional table of environment variables to set when running the test
    binaries. Keys are the environment variable names and values are what they
    should be set to. If omitted or empty, no additional environment variables
    are set.

Example::

    name = "my-rig"

    [ubuntu]
    test_binary_path = "/opt/rocm/bin"
    test_binaries = ["test_foo", "test_bar"]
    test_package_name = "rocm-tests"
    test_debug_package_names = ["rocm-tests-dbgsym"]
    extra_env_var = {HSA_ENABLE_SDMA = "0", LD_LIBRARY_PATH = "/opt/rocm/lib"}

Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`testrig` provides the following commands:

  - `run` to run the described test
  - `check` to verify that the environment is ready to run the described test


Options
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

--filename=<path to file>
    Path to the configuration for the test to run

--debug
    Enable debug mode

--no-root
    Do not run test as root

--dry-run
    Describe the test to be run without actually execting anything

run
-----

--no-debug
    Do not attempt to gather debug information on failed tests

check
------

--ignore-debug-pacakges
    Do not fail if there are missing debug packages

--ignore-test-packages
    Do not fail if there are missing required packages for the test


Copyright
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Copyright (c) Advanced Micro Devices, Inc.
