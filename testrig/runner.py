# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os
import shlex


class BaseRunner:
    """Knows how to find, validate, run, judge and debug one kind of test."""

    name = None
    tests_field = None
    supports_gdb = False
    # used when the rig file doesn't set a top-level "results" format
    default_results = "returncode"

    def __init__(self, spec, rig_dir):
        self.spec = spec
        self.rig_dir = rig_dir

    def test_dir(self):
        raise NotImplementedError

    def required_packages(self):
        raise NotImplementedError

    def debug_packages(self):
        raise NotImplementedError

    def build_command(self, test_path):
        raise NotImplementedError

    def check_runnable(self, test_path):
        raise NotImplementedError

    def debug_command(self, test_path, gdb_batch_file_path):
        return ["gdb", "--batch", f"--command={gdb_batch_file_path}", test_path]

    def execution_state(self, return_code, results):
        """Judge one test from its return code and parsed results (None for returncode-only)."""
        if return_code != 0:
            return "FAIL"
        if results is None:
            return "PASS"
        if results.status != "ok" or results.count("FAIL"):
            return "WARN"
        if results.cases and results.count("SKIP") == len(results.cases):
            return "SKIP"
        return "PASS"


class BinaryRunner(BaseRunner):
    name = "binary"
    tests_field = "test_binaries"
    supports_gdb = True

    def test_dir(self):
        # resolved against cwd (not the rig file) for backwards compatibility
        return os.path.abspath(self.spec["test_binary_path"])

    def required_packages(self):
        return [self.spec["test_package_name"]]

    def debug_packages(self):
        return self.spec["test_debug_package_names"]

    def build_command(self, test_path):
        return [test_path]

    def check_runnable(self, test_path):
        if not os.path.isfile(test_path):
            return "test binary does not exist"
        if not os.access(test_path, os.X_OK):
            return "test binary is not executable"
        return None


class ScriptRunner(BaseRunner):
    name = "script"
    tests_field = "tests"

    def __init__(self, spec, rig_dir):
        super().__init__(spec, rig_dir)
        interpreter = spec.get("interpreter", [])
        if isinstance(interpreter, str):
            interpreter = shlex.split(interpreter)
        self.interpreter = list(interpreter)

    def test_dir(self):
        return os.path.normpath(os.path.join(self.rig_dir, self.spec.get("test_path", ".")))

    def required_packages(self):
        return list(self.spec.get("test_packages", []))

    def debug_packages(self):
        return list(self.spec.get("test_debug_package_names", []))

    def build_command(self, test_path):
        return self.interpreter + [test_path]

    def check_runnable(self, test_path):
        if not os.path.isfile(test_path):
            return "test script does not exist"
        if not self.interpreter and not os.access(test_path, os.X_OK):
            return "test script is not executable and no interpreter is set"
        return None


RUNNERS = {runner.name: runner for runner in (BinaryRunner, ScriptRunner)}


def make_runner(spec, rig_dir):
    runner_name = spec.get("runner", "binary")
    if runner_name not in RUNNERS:
        raise Exception(f'unknown runner "{runner_name}", expected one of: {", ".join(RUNNERS)}')
    return RUNNERS[runner_name](spec, rig_dir)
