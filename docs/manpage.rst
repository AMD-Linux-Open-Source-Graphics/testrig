
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
