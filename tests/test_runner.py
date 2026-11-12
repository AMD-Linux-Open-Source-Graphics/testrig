# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os

import pytest

from testrig.results import CaseResult, ParsedResults
from testrig.runner import BinaryRunner, ScriptRunner, make_runner


def parsed(*case_states, status="ok"):
    return ParsedResults(status, [CaseResult(name=f"c{i}", classname=None, state=s) for i, s in enumerate(case_states)])


class TestExecutionState:
    runner = BinaryRunner({}, "/rig")

    def test_returncode_only(self):
        assert self.runner.execution_state(0, None) == "PASS"
        assert self.runner.execution_state(1, None) == "FAIL"

    def test_nonzero_exit_always_fails(self):
        assert self.runner.execution_state(1, parsed("PASS")) == "FAIL"
        assert self.runner.execution_state(-11, parsed(status="missing")) == "FAIL"

    def test_zero_exit_with_failed_cases_warns(self):
        assert self.runner.execution_state(0, parsed("PASS", "FAIL")) == "WARN"

    def test_zero_exit_with_unusable_results_warns(self):
        assert self.runner.execution_state(0, parsed(status="missing")) == "WARN"
        assert self.runner.execution_state(0, parsed(status="invalid")) == "WARN"

    def test_all_skipped(self):
        assert self.runner.execution_state(0, parsed("SKIP", "SKIP")) == "SKIP"

    def test_some_skipped_passes(self):
        assert self.runner.execution_state(0, parsed("PASS", "SKIP")) == "PASS"

    def test_no_cases_passes(self):
        assert self.runner.execution_state(0, parsed()) == "PASS"


def test_default_results_is_returncode():
    assert BinaryRunner.default_results == "returncode"
    assert ScriptRunner.default_results == "returncode"


def test_debug_command():
    command = BinaryRunner({}, "/rig").debug_command("/bin/t", "/tmp/run_debug.gdb")
    assert command == ["gdb", "--batch", "--command=/tmp/run_debug.gdb", "/bin/t"]


class TestMakeRunner:
    def test_defaults_to_binary(self):
        assert isinstance(make_runner({}, "/rig"), BinaryRunner)

    def test_selects_script(self):
        assert isinstance(make_runner({"runner": "script"}, "/rig"), ScriptRunner)

    def test_unknown_runner_raises(self):
        with pytest.raises(Exception, match='unknown runner "nope"'):
            make_runner({"runner": "nope"}, "/rig")


class TestBinaryRunner:
    def test_test_dir_resolved_against_cwd(self):
        runner = BinaryRunner({"test_binary_path": "bin"}, "/rig")
        assert runner.test_dir() == os.path.abspath("bin")

    def test_packages(self):
        runner = BinaryRunner({"test_package_name": "pkg", "test_debug_package_names": ["pkg-dbg"]}, "/rig")
        assert runner.required_packages() == ["pkg"]
        assert runner.debug_packages() == ["pkg-dbg"]

    def test_build_command(self):
        assert BinaryRunner({}, "/rig").build_command("/bin/t") == ["/bin/t"]


class TestScriptRunner:
    def test_test_dir_defaults_to_rig_dir(self):
        assert ScriptRunner({}, "/rig").test_dir() == "/rig"

    def test_test_dir_relative_to_rig_dir(self):
        assert ScriptRunner({"test_path": "tests"}, "/rig").test_dir() == "/rig/tests"

    def test_test_dir_absolute(self):
        assert ScriptRunner({"test_path": "/opt/tests"}, "/rig").test_dir() == "/opt/tests"

    def test_packages_optional(self):
        runner = ScriptRunner({}, "/rig")
        assert runner.required_packages() == []
        assert runner.debug_packages() == []

    def test_packages(self):
        runner = ScriptRunner({"test_packages": ["python3-numpy", "bash"]}, "/rig")
        assert runner.required_packages() == ["python3-numpy", "bash"]

    def test_build_command_without_interpreter(self):
        assert ScriptRunner({}, "/rig").build_command("/rig/t.sh") == ["/rig/t.sh"]

    def test_build_command_with_string_interpreter(self):
        runner = ScriptRunner({"interpreter": "python3 -u"}, "/rig")
        assert runner.build_command("/rig/t.py") == ["python3", "-u", "/rig/t.py"]

    def test_build_command_with_list_interpreter(self):
        runner = ScriptRunner({"interpreter": ["bash", "-eu"]}, "/rig")
        assert runner.build_command("/rig/t.sh") == ["bash", "-eu", "/rig/t.sh"]

    def test_does_not_support_gdb(self):
        assert ScriptRunner.supports_gdb is False

    def test_missing_script(self, tmp_path):
        reason = ScriptRunner({}, str(tmp_path)).check_runnable(str(tmp_path / "missing.py"))
        assert reason == "test script does not exist"

    def test_non_executable_without_interpreter(self, tmp_path):
        script = tmp_path / "t.py"
        script.write_text("print('hi')\n")
        script.chmod(0o644)

        reason = ScriptRunner({}, str(tmp_path)).check_runnable(str(script))

        assert "not executable" in reason

    def test_non_executable_with_interpreter_is_runnable(self, tmp_path):
        script = tmp_path / "t.py"
        script.write_text("print('hi')\n")
        script.chmod(0o644)

        assert ScriptRunner({"interpreter": "python3"}, str(tmp_path)).check_runnable(str(script)) is None
