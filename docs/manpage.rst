
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
(for example ``[ubuntu]`` or ``[fedora]``). The following optional top-level
field is also supported:

results
    How each test's result is determined: ``returncode`` (default) uses only
    the exit code; ``junit`` also parses a JUnit XML file (pytest, gtest and
    ctest formats) written by the test. Its path is substituted for
    ``{results_file}`` in ``interpreter`` and ``extra_args`` and exported as
    ``TESTRIG_RESULTS_FILE``. With ``junit``, a non-zero exit is ``FAIL``; exit
    0 with failed cases or a missing/unreadable results file is ``WARN`` (no
    non-zero testrig exit, no debug run); exit 0 with every case skipped is
    ``SKIP``; anything else is ``PASS``.

Each distro section may set:

runner
    Kind of test to run: ``binary`` (default) or ``script``. The runner
    determines which of the fields below apply.

The ``binary`` runner (the default) supports the following fields:

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
    are set. Applies to all runners.

The ``script`` runner is for tests written in interpreted languages such as
Python or bash. It supports the following fields (plus ``extra_env_var``):

tests
    Allowlist of script names to run, combined with ``test_path``.

test_path
    Optional directory containing the scripts. Relative paths are resolved
    against the directory of the rig file. Defaults to that directory.

interpreter
    Optional command used to run each script, as a string (``"python3 -u"``)
    or a list (``["bash", "-eu"]``). When omitted, scripts must be executable
    and are run directly via their shebang.

test_packages
    Optional list of packages that must be installed to run the scripts.

Debug information gathering (gdb) is skipped for ``script`` tests.

Example::

    name = "my-rig"

    [ubuntu]
    test_binary_path = "/opt/rocm/bin"
    test_binaries = ["test_foo", "test_bar"]
    test_package_name = "rocm-tests"
    test_debug_package_names = ["rocm-tests-dbgsym"]
    extra_env_var = {HSA_ENABLE_SDMA = "0", LD_LIBRARY_PATH = "/opt/rocm/lib"}

    [fedora]
    runner = "script"
    interpreter = "python3"
    test_path = "tests"
    tests = ["check_devices.py"]
    test_packages = ["python3-numpy"]

Global Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Testrig reads optional global settings from ``/etc/testrig/settings.toml`` and
``~/.config/testrig/settings.toml``. Values in the user file override values in
the system file. The following settings are supported:

disable_debug
    Disable gathering of debug information (gdb runs) on failed tests. Defaults
    to ``false``.

ROCR_VISIBLE_DEVICES
    GPU UUID (or list accepted by ROCr) to expose during test binary execution.
    Defaults to empty, in which case testrig takes no additional action.

gdb_pyfile_dir
    Directory containing the ``gdb_traceback_on_stop.py`` helper that testrig
    sources when gathering debug information on failed tests. Defaults to
    ``/usr/share/testrig``.

enable_file_output
    Enable writing output files (run log, output directory) to disk during
    rig execution. Defaults to ``false``, meaning no files are created on the
    filesystem unless overridden by this setting or the ``--file-output``
    command-line option.

output_dir
    Base directory for storing output files when file output is enabled.
    Defaults to ``./testrig-logs``. Overridden by the ``--output-dir``
    command-line option when given.

enable_gpu_monitoring
    Sample GPU usage (utilization, VRAM, temperature, power) via ``amd-smi``
    while each test binary runs. Aggregated per-binary statistics are recorded
    in the run summary. When ``enable_file_output`` is also set, the full
    time-series is streamed to ``testrig_gpu_samples.jsonl`` (one JSON object
    per line) in the run output directory. Monitoring is best-effort: if
    ``amd-smi`` is missing or fails, the test run still completes and the
    failure is reported in the summary. Defaults to ``false``.

gpu_monitoring_interval
    Seconds between ``amd-smi`` samples when GPU monitoring is enabled.
    Defaults to ``1.0``.

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

--output-dir=<path to directory>
    Base directory for storing output files. Overrides the ``output_dir``
    setting; if unset, the setting (default: ``./testrig-logs``) is used.
    If this directory does not yet exist it is created and used directly. If
    it already exists, output is written to a sibling directory named
    ``<output-dir>-YYYYMMDD_HHmm`` using the local time the run started
    (``YYYYMMDD`` date, ``HHmm`` hour and minute); a ``-N`` counter is
    appended if a run in the same minute already created that directory.

--file-output / --no-file-output
    Enable or disable writing output files to disk for this run. Overrides
    the ``enable_file_output`` setting; if neither flag is given, the setting
    (default: disabled) is used.

--gpu-monitoring / --no-gpu-monitoring
    Enable or disable sampling GPU usage (via ``amd-smi``) while tests run.
    Overrides the ``enable_gpu_monitoring`` setting; if neither flag is given,
    the setting (default: disabled) is used.

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
