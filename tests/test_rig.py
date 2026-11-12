# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Characterization tests for testrig.rig.

These tests document actual behavior, not desired behavior. Bugs are
asserted as-is and flagged with comments.
"""

import logging
import os
import subprocess
import uuid
from unittest.mock import MagicMock, patch

import pytest

from testrig.rig import Rig, parse_rig

TEST_UUID = uuid.uuid7()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def make_rig(name="testrun", spec=None, dry_run=False, run_uuid=TEST_UUID):
    if spec is None:
        spec = {"name": name}
    return Rig(name, spec, dry_run, run_uuid)


def run_results(passed=(), failed=(), warned=(), skipped=()):
    return {"passed": list(passed), "failed": list(failed), "warned": list(warned), "skipped": list(skipped)}


def make_mock_distro(name="ubuntu"):
    distro = MagicMock()
    distro.name = name
    return distro


def make_popen_mock(mock_popen, returncode=0, stdout_lines=None):
    """Configure mock_popen (a patched subprocess.Popen) to behave like a real Popen."""
    process = MagicMock()
    process.stdout.__iter__.return_value = iter(stdout_lines or [])
    process.returncode = returncode
    process.wait.return_value = returncode
    mock_popen.return_value = process
    return process


@pytest.fixture
def assume_binaries_present():
    """Treat test binaries as existing and executable so tests exercising
    execution logic are unaffected by the binary existence check."""
    with patch("testrig.rig.os.path.isfile", return_value=True), patch(
        "testrig.rig.os.access", return_value=True
    ):
        yield


# ==========================================================================
# Group A: parse_rig()
# ==========================================================================


class TestParseRun:
    def test_valid_toml_returns_test_rig(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(
            b'name = "mytest"\n[ubuntu]\ntest_binary_path = "/opt/bin"\ntest_package_name = "mypkg"\n'
        )

        result = parse_rig(str(toml_file), TEST_UUID)

        assert isinstance(result, Rig)
        assert result.name == "mytest"
        assert result.rig_spec["name"] == "mytest"
        assert result.rig_spec["ubuntu"]["test_binary_path"] == "/opt/bin"
        assert result.dry_run is False
        assert result.inputfile_path == os.path.abspath(str(toml_file))
        assert result.rig_dir == os.path.dirname(os.path.abspath(str(toml_file)))

    def test_valid_toml_with_dry_run(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'name = "drytest"\n')

        result = parse_rig(str(toml_file), TEST_UUID, dry_run=True)

        assert result.dry_run is True
        assert result.name == "drytest"

    def test_passes_settings_to_rig(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'name = "settingstest"\n')
        settings = {"ROCR_VISIBLE_DEVICES": "GPU-abc"}

        result = parse_rig(str(toml_file), TEST_UUID, settings=settings)

        assert result.settings["ROCR_VISIBLE_DEVICES"] == "GPU-abc"

    def test_missing_name_field_raises(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'[ubuntu]\ntest_binary_path = "/opt/bin"\n')

        with pytest.raises(Exception, match='Field "name" is required'):
            parse_rig(str(toml_file), TEST_UUID)


# ==========================================================================
# Group B: _setup()
# ==========================================================================


class TestSetup:
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake-workdir")
    @patch("testrig.rig.get_distro")
    def test_sets_distro_and_binary_path_from_spec(self, mock_get_distro, mock_mkdtemp):
        mock_distro = make_mock_distro("ubuntu")
        mock_get_distro.return_value = mock_distro

        spec = {
            "name": "test1",
            "ubuntu": {"test_binary_path": "/opt/rocm/bin", "test_package_name": "pkg"},
        }
        run = make_rig(spec=spec)
        run._setup()

        assert run.distro is mock_distro
        assert run.binary_path == os.path.abspath("/opt/rocm/bin")
        assert run.workdir == "/tmp/fake-workdir"
        mock_get_distro.assert_called_once_with(no_root=False)

    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake-workdir")
    @patch("testrig.rig.get_distro")
    def test_defaults_binary_path_when_no_distro_spec(self, mock_get_distro, mock_mkdtemp, caplog):
        mock_distro = make_mock_distro("ubuntu")
        mock_get_distro.return_value = mock_distro

        spec = {"name": "test2"}
        run = make_rig(spec=spec)
        with caplog.at_level(logging.INFO):
            run._setup()

        assert run.binary_path == os.path.abspath(".")
        assert "no distro specified" in caplog.text

    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake-workdir")
    @patch("testrig.rig.get_distro")
    def test_passes_no_root_to_get_distro(self, mock_get_distro, mock_mkdtemp):
        mock_get_distro.return_value = make_mock_distro("ubuntu")

        run = make_rig(spec={"name": "test3"})
        run.no_root = True
        run._setup()

        mock_get_distro.assert_called_once_with(no_root=True)


# ==========================================================================
# Group C: verify_packages()
# ==========================================================================


class TestVerifyPackages:
    def test_package_installed_not_dry_run(self, caplog):
        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True
        distro.get_package_info.return_value = "1.2.3-1"

        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/bin", "test_package_name": "mypkg"},
        }
        run = make_rig(spec=spec)
        run.distro = distro

        with caplog.at_level(logging.INFO):
            run.verify_packages()

        # dry_run=False → do_install_missing_packages = not False = True
        distro.check_for_installed_packages.assert_called_once_with(["mypkg"], install_if_not_present=True)
        distro.get_package_info.assert_called_once_with("mypkg")
        assert 'required test package "mypkg" is installed: 1.2.3-1' in caplog.text

    def test_package_installed_dry_run(self):
        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True
        distro.get_package_info.return_value = "1.2.3-1"

        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/bin", "test_package_name": "mypkg"},
        }
        run = make_rig(spec=spec, dry_run=True)
        run.distro = distro

        run.verify_packages()

        # dry_run=True → do_install_missing_packages = not True = False
        distro.check_for_installed_packages.assert_called_once_with(["mypkg"], install_if_not_present=False)

    def test_no_distro_in_spec(self, caplog):
        distro = make_mock_distro("ubuntu")
        run = make_rig(spec={"name": "test"})
        run.distro = distro

        with caplog.at_level(logging.INFO):
            run.verify_packages()

        assert "no distro information specified" in caplog.text

    def test_initializes_distro_if_none(self):
        run = make_rig(spec={"name": "test"})
        run.distro = None

        with patch.object(run, "_setup") as mock_init:

            def set_distro():
                run.distro = make_mock_distro("ubuntu")

            mock_init.side_effect = set_distro

            run.verify_packages()
            mock_init.assert_called_once()


# ==========================================================================
# Group D: _execute_binary()
# ==========================================================================


@pytest.mark.usefixtures("assume_binaries_present")
class TestExecuteBinary:
    @patch("testrig.rig.subprocess.Popen")
    def test_pass_returns_true(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()

        result = run._execute_binary("/fake/bin/test_a")

        assert result is True
        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=expected_env,
            text=True,
            bufsize=1,
        )

    @patch("testrig.rig.subprocess.Popen")
    def test_fail_returns_false(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=1)
        run = make_rig()

        result = run._execute_binary("/fake/bin/test_a")

        assert result is False

    @patch("testrig.rig.subprocess.Popen")
    def test_extra_args_appended(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        spec = {"name": "test", "extra_args": ["--gtest_filter=Foo", "--verbose"]}
        run = make_rig(spec=spec)

        run._execute_binary("/fake/bin/test_a")

        expected_cmd = ["/fake/bin/test_a", "--gtest_filter=Foo", "--verbose"]
        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(
            expected_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=expected_env, text=True, bufsize=1
        )

    @patch("testrig.rig.subprocess.Popen")
    def test_sets_rocr_visible_devices_when_configured(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig(spec={"name": "test"})
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._execute_binary("/fake/bin/test_a")

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=expected_env,
            text=True,
            bufsize=1,
        )

    @patch("testrig.rig.subprocess.Popen")
    def test_no_gpu_monitoring_key_when_disabled(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()

        run._execute_binary("/fake/bin/test_a")

        assert "gpu_monitoring" not in run.test_results[0]

    @patch("testrig.rig.GpuMonitor")
    @patch("testrig.rig.subprocess.Popen")
    def test_records_gpu_monitoring_when_enabled(self, mock_subproc, mock_monitor):
        make_popen_mock(mock_subproc, returncode=0)
        aggregate = {
            "status": "ok",
            "error": None,
            "samples_collected": 3,
            "interval_seconds": 1.0,
            "gpus": [],
        }
        instance = mock_monitor.return_value
        instance.__enter__.return_value = instance
        instance.__exit__.return_value = False
        instance.aggregate.return_value = aggregate
        run = make_rig()
        run.gpu_monitoring = True

        run._execute_binary("/fake/bin/test_a", sample_sink="SINK")

        assert run.test_results[0]["gpu_monitoring"] == aggregate
        mock_monitor.assert_called_once_with(1.0, sample_sink="SINK", binary="/fake/bin/test_a")

    @patch("testrig.gpumonitor.shutil.which", return_value=None)
    @patch("testrig.rig.subprocess.Popen")
    def test_survives_unavailable_amd_smi(self, mock_subproc, mock_which):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()
        run.gpu_monitoring = True

        result = run._execute_binary("/fake/bin/test_a")

        assert result is True
        assert run.test_results[0]["gpu_monitoring"]["status"] == "unavailable"


# ==========================================================================
# Group D2: GPU sample sink (no empty file left behind)
# ==========================================================================


class TestGpuSampleSink:
    def test_lazy_sink_does_not_create_file_until_write(self, tmp_path):
        from testrig.rig import _LazyJsonlSink

        path = tmp_path / "samples.jsonl"
        sink = _LazyJsonlSink(str(path))
        sink.flush()
        sink.close()

        assert not path.exists()

    def test_lazy_sink_creates_file_on_write(self, tmp_path):
        from testrig.rig import _LazyJsonlSink

        path = tmp_path / "samples.jsonl"
        sink = _LazyJsonlSink(str(path))
        sink.write('{"a": 1}\n')
        sink.flush()
        sink.close()

        assert path.read_text() == '{"a": 1}\n'

    @patch("testrig.gpumonitor.shutil.which", return_value=None)
    @patch("testrig.rig.subprocess.Popen")
    def test_run_tests_leaves_no_file_when_amd_smi_unavailable(self, mock_subproc, mock_which, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)
        spec = {"name": "t", "ubuntu": {"test_binary_path": "/bin", "test_binaries": ["a"]}}
        run = Rig(
            "t", spec, False, TEST_UUID, output_dir=str(tmp_path), file_output=True, gpu_monitoring=True
        )
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = "/bin"

        run.run_tests()

        assert not (tmp_path / "testrig_gpu_samples.jsonl").exists()
        assert run.test_results[0]["gpu_monitoring"]["status"] == "unavailable"


# ==========================================================================
# Group D3: GPU monitoring logging
# ==========================================================================


class TestGpuMonitoringLogging:
    def test_announces_enabled_and_output_path(self, tmp_path, caplog):
        run = Rig(
            "t", {"name": "t"}, False, TEST_UUID, output_dir=str(tmp_path), file_output=True, gpu_monitoring=True
        )

        with caplog.at_level(logging.INFO):
            run._log_gpu_monitoring_config()

        assert "ENABLED" in caplog.text
        assert str(tmp_path / "testrig_gpu_samples.jsonl") in caplog.text

    def test_announces_disabled(self, caplog):
        run = make_rig()

        with caplog.at_level(logging.INFO):
            run._log_gpu_monitoring_config()

        assert "GPU monitoring: disabled" in caplog.text

    def test_announces_no_file_when_file_output_off(self, caplog):
        run = Rig("t", {"name": "t"}, False, TEST_UUID, gpu_monitoring=True, file_output=False)

        with caplog.at_level(logging.INFO):
            run._log_gpu_monitoring_config()

        assert "no time-series file" in caplog.text

    @patch("testrig.gpumonitor.shutil.which", return_value=None)
    @patch("testrig.rig.subprocess.Popen")
    def test_unavailable_is_logged_at_warning_visible_at_info(self, mock_subproc, mock_which, caplog):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()
        run.gpu_monitoring = True

        with caplog.at_level(logging.INFO):
            run._execute_binary("/fake/bin/test_a")

        monitoring_warnings = [
            record
            for record in caplog.records
            if record.levelno >= logging.WARNING and "GPU monitoring" in record.getMessage()
        ]
        assert monitoring_warnings


class TestExecuteBinaryMissing:
    @patch("testrig.rig.subprocess.Popen")
    def test_missing_binary_returns_false_and_does_not_run(self, mock_subproc):
        run = make_rig()

        with patch("testrig.rig.os.path.isfile", return_value=False):
            result = run._execute_binary("/fake/bin/missing")

        assert result is False
        mock_subproc.assert_not_called()

    @patch("testrig.rig.subprocess.Popen")
    def test_missing_binary_logs_error(self, mock_subproc, caplog):
        run = make_rig()

        with caplog.at_level(logging.ERROR), patch("testrig.rig.os.path.isfile", return_value=False):
            run._execute_binary("/fake/bin/missing")

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert "does not exist" in error_records[0].getMessage()
        assert "/fake/bin/missing" in error_records[0].getMessage()

    @patch("testrig.rig.subprocess.Popen")
    def test_missing_binary_records_failed_result(self, mock_subproc):
        run = make_rig()

        with patch("testrig.rig.os.path.isfile", return_value=False):
            run._execute_binary("/fake/bin/missing")

        assert len(run.test_results) == 1
        result = run.test_results[0]
        assert result["binary"] == "/fake/bin/missing"
        assert result["execution_state"] == "FAIL"
        assert result["return_code"] is None

    @patch("testrig.rig.subprocess.Popen")
    def test_non_executable_binary_returns_false_and_does_not_run(self, mock_subproc):
        run = make_rig()

        with patch("testrig.rig.os.path.isfile", return_value=True), patch(
            "testrig.rig.os.access", return_value=False
        ):
            result = run._execute_binary("/fake/bin/not_exec")

        assert result is False
        mock_subproc.assert_not_called()

    @patch("testrig.rig.subprocess.Popen")
    def test_non_executable_binary_logs_error(self, mock_subproc, caplog):
        run = make_rig()

        with caplog.at_level(logging.ERROR), patch("testrig.rig.os.path.isfile", return_value=True), patch(
            "testrig.rig.os.access", return_value=False
        ):
            run._execute_binary("/fake/bin/not_exec")

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) == 1
        assert "not executable" in error_records[0].getMessage()


# ==========================================================================
# Group E: _resolve_test_binaries()
# ==========================================================================


class TestResolveTestBinaries:
    def test_joins_binary_names_to_binary_path(self):
        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_binaries": ["test_foo", "test_bar"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = "/opt/bin"

        run._resolve_test_binaries()

        assert run.test_binaries == ["/opt/bin/test_foo", "/opt/bin/test_bar"]

    def test_empty_allowlist_produces_empty_list(self):
        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/opt/bin", "test_binaries": []},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = "/opt/bin"

        run._resolve_test_binaries()

        assert run.test_binaries == []

    def test_missing_test_binaries_key_raises(self):
        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/opt/bin"},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = "/opt/bin"

        with pytest.raises(Exception, match='"test_binaries" is not specified'):
            run._resolve_test_binaries()

    def test_missing_distro_section_raises(self):
        spec = {"name": "test"}
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = os.path.abspath(".")

        with pytest.raises(Exception, match="no distro section for ubuntu"):
            run._resolve_test_binaries()


# ==========================================================================
# Group F: run_tests()
# ==========================================================================


@pytest.mark.usefixtures("assume_binaries_present")
class TestRunTests:
    @patch("testrig.rig.subprocess.Popen")
    def test_all_pass(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == run_results(passed=["/bin/test_a", "/bin/test_b"])

    @patch("testrig.rig.subprocess.Popen")
    def test_all_fail(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=1)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == run_results(failed=["/bin/test_a", "/bin/test_b"])

    @patch("testrig.rig.subprocess.Popen")
    def test_mixed_results(self, mock_subproc):
        mock_subproc.side_effect = [
            make_popen_mock(MagicMock(), returncode=0),
            make_popen_mock(MagicMock(), returncode=1),
        ]

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == run_results(passed=["/bin/test_a"], failed=["/bin/test_b"])

    @patch("testrig.rig.subprocess.Popen")
    def test_total_tests_print_bug(self, mock_subproc, caplog):
        """BUG: 'total tests run: '.format(num_tests_run) has no {} placeholder.
        The count is silently lost."""
        make_popen_mock(mock_subproc, returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a"]

        with caplog.at_level(logging.INFO):
            run.run_tests()

        assert "total tests run: 1" in caplog.text

    def test_resolves_binaries_if_none(self):
        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = None

        with patch.object(run, "_resolve_test_binaries") as mock_resolve:

            def set_binaries():
                run.test_binaries = []

            mock_resolve.side_effect = set_binaries

            result = run.run_tests()
            mock_resolve.assert_called_once()
            assert result == run_results()

    @patch("testrig.rig.subprocess.Popen")
    def test_missing_binary_marked_failed(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/missing"]

        def isfile(path):
            return path != "/bin/missing"

        with patch("testrig.rig.os.path.isfile", side_effect=isfile):
            result = run.run_tests()

        assert result == run_results(passed=["/bin/test_a"], failed=["/bin/missing"])


# ==========================================================================
# Group G: execute()
# ==========================================================================


@pytest.mark.usefixtures("assume_binaries_present")
class TestExecute:
    @patch("testrig.rig.subprocess.Popen")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_normal_mode_returns_results(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        make_popen_mock(mock_subproc, returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_package_name": "mypkg",
                "test_binaries": ["test_a"],
            },
        }
        run = make_rig(spec=spec)

        result = run.execute(force_debug=False)

        assert result == run_results(passed=["/opt/bin/test_a"])

    @patch("testrig.rig.subprocess.Popen")
    @patch("testrig.rig.tempfile.mkdtemp")
    @patch("testrig.rig.get_distro")
    def test_force_debug_returns_empty_results(self, mock_get_distro, mock_mkdtemp, mock_subproc, tmp_path):
        """When force_debug=True, execute gathers debug info instead of running
        tests and returns an empty results dict."""
        mock_mkdtemp.return_value = str(tmp_path)
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro
        make_popen_mock(mock_subproc, returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_package_name": "mypkg",
                "test_debug_package_names": ["mypkg-dbg"],
                "test_binaries": ["test_a"],
            },
        }
        run = make_rig(spec=spec)

        result = run.execute(force_debug=True)

        assert result == run_results()

    @patch("testrig.rig.subprocess.Popen")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_disable_debug_overrides_force_debug(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        """When disable_debug=True, force_debug is ignored and tests are run."""
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        make_popen_mock(mock_subproc, returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_package_name": "mypkg",
                "test_binaries": ["test_a"],
            },
        }
        run = make_rig(spec=spec)

        result = run.execute(force_debug=True, disable_debug=True)

        assert result == run_results(passed=["/opt/bin/test_a"])

    @patch("testrig.rig.subprocess.Popen")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_disable_debug_runs_tests(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        """When disable_debug=True and force_debug=False, tests run normally."""
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        make_popen_mock(mock_subproc, returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_package_name": "mypkg",
                "test_binaries": ["test_a"],
            },
        }
        run = make_rig(spec=spec)

        result = run.execute(force_debug=False, disable_debug=True)

        assert result == run_results(passed=["/opt/bin/test_a"])


# ==========================================================================
# Group H: verify_debug_packages()
# ==========================================================================


class TestVerifyDebugPackages:
    def test_no_distro_in_spec(self, caplog):
        distro = make_mock_distro("ubuntu")
        run = make_rig(spec={"name": "test"})
        run.distro = distro

        with caplog.at_level(logging.INFO):
            run.verify_debug_packages()

        assert "no distro information specified" in caplog.text

    def test_debug_packages_checked(self, caplog):
        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg", "lib-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro

        with caplog.at_level(logging.INFO):
            run.verify_debug_packages()

        distro.check_for_installed_packages.assert_called_once_with(["pkg-dbg", "lib-dbg"], install_if_not_present=True)
        assert 'required debug package "pkg-dbg lib-dbg" is installed.' in caplog.text


# ==========================================================================
# Group I: gather_debug_info()
# ==========================================================================


class TestGatherDebugInfo:
    @patch("testrig.rig.subprocess.Popen")
    def test_writes_gdb_batch_and_runs(self, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)

        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro
        run.workdir = str(tmp_path)

        run.gather_debug_info(["/bin/test_a", "/bin/test_b"])

        # Verify gdb batch file was written
        batch_file = tmp_path / "run_debug.gdb"
        assert batch_file.exists()
        content = batch_file.read_text()
        assert "source" in content
        assert "gdb_traceback_on_stop.py" in content
        assert "\nrun\n" in content

        # Verify gdb was called once per failed binary
        gdb_calls = [c for c in mock_subproc.call_args_list if c[0][0][0] == "gdb"]
        assert len(gdb_calls) == 2

    @patch("testrig.rig.subprocess.Popen")
    def test_gdb_failure_prints_message(self, mock_subproc, tmp_path, caplog):
        make_popen_mock(mock_subproc, returncode=1)

        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro
        run.workdir = str(tmp_path)

        run.gather_debug_info(["/bin/test_a"])

        assert "gdb failed for /bin/test_a with return code 1" in caplog.text

    @patch("testrig.rig.subprocess.Popen")
    def test_defaults_gdb_pyfile_dir(self, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)

        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro
        run.workdir = str(tmp_path)

        run.gather_debug_info(["/bin/test_a"])

        content = (tmp_path / "run_debug.gdb").read_text()
        assert "source /usr/share/testrig/gdb_traceback_on_stop.py" in content

    @patch("testrig.rig.subprocess.Popen")
    def test_uses_configured_gdb_pyfile_dir(self, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)

        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro
        run.workdir = str(tmp_path)
        run.settings = {"gdb_pyfile_dir": "/opt/testrig"}

        run.gather_debug_info(["/bin/test_a"])

        content = (tmp_path / "run_debug.gdb").read_text()
        assert "source /opt/testrig/gdb_traceback_on_stop.py" in content


# ==========================================================================
# Group J: prepare()
# ==========================================================================


class TestPrepare:
    @patch("testrig.rig.subprocess.Popen")
    def test_calls_rocminfo(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.dry_run = False

        run.prepare()

        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(
            ["rocminfo"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=expected_env, text=True, bufsize=1
        )

    @patch("testrig.rig.subprocess.Popen")
    def test_skips_rocminfo_in_dry_run(self, mock_subproc, caplog):
        run = make_rig(dry_run=True)
        run.distro = make_mock_distro()

        with caplog.at_level(logging.INFO):
            run.prepare()

        mock_subproc.assert_not_called()
        assert "rocminfo" in caplog.text


# ==========================================================================
# Group K: environment handling for subprocess calls
# ==========================================================================


class TestBuildRunEnv:
    def test_inherits_current_environment(self):
        run = make_rig()

        with patch.dict(os.environ, {"SOME_VAR": "some_value"}, clear=False):
            env = run._build_run_env()

        assert env["SOME_VAR"] == "some_value"

    def test_returns_a_copy_not_the_live_environment(self):
        run = make_rig()

        env = run._build_run_env()
        env["TESTRIG_ONLY"] = "1"

        assert "TESTRIG_ONLY" not in os.environ

    def test_omits_rocr_visible_devices_when_unset(self):
        run = make_rig()

        env = run._build_run_env()

        assert "ROCR_VISIBLE_DEVICES" not in env

    def test_omits_rocr_visible_devices_when_empty_string(self):
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": ""}

        env = run._build_run_env()

        assert "ROCR_VISIBLE_DEVICES" not in env

    def test_sets_rocr_visible_devices_when_configured(self):
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        env = run._build_run_env()

        assert env["ROCR_VISIBLE_DEVICES"] == "GPU-123"

    def test_overrides_inherited_rocr_visible_devices(self):
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-from-settings"}

        with patch.dict(os.environ, {"ROCR_VISIBLE_DEVICES": "GPU-from-shell"}, clear=False):
            env = run._build_run_env()

        assert env["ROCR_VISIBLE_DEVICES"] == "GPU-from-settings"

    def test_sets_extra_env_var_from_distro_spec(self):
        spec = {
            "name": "test",
            "ubuntu": {"extra_env_var": {"MY_VAR": "my_value", "OTHER_VAR": "other_value"}},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")

        env = run._build_run_env()

        assert env["MY_VAR"] == "my_value"
        assert env["OTHER_VAR"] == "other_value"

    def test_omits_extra_env_var_when_not_specified(self):
        spec = {"name": "test", "ubuntu": {"test_binary_path": "/bin"}}
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")

        env = run._build_run_env()

        assert "MY_VAR" not in env

    def test_omits_extra_env_var_when_empty_table(self):
        spec = {"name": "test", "ubuntu": {"extra_env_var": {}}}
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")

        env = run._build_run_env()

        assert "MY_VAR" not in env

    def test_omits_extra_env_var_when_distro_is_none(self):
        spec = {
            "name": "test",
            "ubuntu": {"extra_env_var": {"MY_VAR": "my_value"}},
        }
        run = make_rig(spec=spec)
        run.distro = None

        env = run._build_run_env()

        assert "MY_VAR" not in env

    def test_omits_extra_env_var_when_distro_not_in_spec(self):
        spec = {
            "name": "test",
            "ubuntu": {"extra_env_var": {"MY_VAR": "my_value"}},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("fedora")

        env = run._build_run_env()

        assert "MY_VAR" not in env

    def test_coerces_non_string_extra_env_var_values(self):
        spec = {
            "name": "test",
            "ubuntu": {"extra_env_var": {"NUM_VAR": 42, "BOOL_VAR": True}},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")

        env = run._build_run_env()

        assert env["NUM_VAR"] == "42"
        assert env["BOOL_VAR"] == "True"

    def test_extra_env_var_overrides_inherited_environment(self):
        spec = {
            "name": "test",
            "ubuntu": {"extra_env_var": {"MY_VAR": "from-spec"}},
        }
        run = make_rig(spec=spec)
        run.distro = make_mock_distro("ubuntu")

        with patch.dict(os.environ, {"MY_VAR": "from-shell"}, clear=False):
            env = run._build_run_env()

        assert env["MY_VAR"] == "from-spec"


class TestRunCommand:
    @patch("testrig.rig.subprocess.Popen")
    def test_passes_built_env_and_redirects_stderr(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._run_command(["some", "command"])

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["some", "command"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=expected_env,
            text=True,
            bufsize=1,
        )

    def test_forwards_check_flag_and_raises_on_failure(self):
        with patch("testrig.rig.subprocess.Popen") as mock_subproc:
            make_popen_mock(mock_subproc, returncode=1)
            run = make_rig()

            with pytest.raises(subprocess.CalledProcessError):
                run._run_command(["some", "command"], check=True)

    def test_check_false_does_not_raise_on_failure(self):
        with patch("testrig.rig.subprocess.Popen") as mock_subproc:
            make_popen_mock(mock_subproc, returncode=1)
            run = make_rig()

            process = run._run_command(["some", "command"], check=False)

            assert process.returncode == 1

    def test_output_lines_are_logged_at_info(self, caplog):
        with patch("testrig.rig.subprocess.Popen") as mock_subproc:
            make_popen_mock(mock_subproc, returncode=0, stdout_lines=["line one\n", "line two\n"])
            run = make_rig()

            with caplog.at_level(logging.INFO):
                run._run_command(["some", "command"])

            assert "line one" in caplog.text
            assert "line two" in caplog.text

    def test_full_output_relogged_at_error_on_failure(self, caplog):
        with patch("testrig.rig.subprocess.Popen") as mock_subproc:
            make_popen_mock(mock_subproc, returncode=1, stdout_lines=["boom\n"])
            run = make_rig()

            with caplog.at_level(logging.INFO):
                run._run_command(["some", "command"])

            error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert len(error_records) == 1
            assert "boom" in error_records[0].getMessage()


@pytest.mark.usefixtures("assume_binaries_present")
class TestSubprocessEnvPropagation:
    @patch("testrig.rig.subprocess.Popen")
    def test_rocminfo_receives_rocr_visible_devices(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig(dry_run=False)
        run.distro = make_mock_distro()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run.prepare()

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["rocminfo"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=expected_env, text=True, bufsize=1
        )

    @patch("testrig.rig.subprocess.Popen")
    def test_gdb_receives_rocr_visible_devices(self, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)

        distro = make_mock_distro("ubuntu")
        distro.check_for_installed_packages.return_value = True

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/bin",
                "test_package_name": "pkg",
                "test_debug_package_names": ["pkg-dbg"],
            },
        }
        run = make_rig(spec=spec)
        run.distro = distro
        run.workdir = str(tmp_path)
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run.gather_debug_info(["/bin/test_a"])

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        gdb_calls = [c for c in mock_subproc.call_args_list if c[0][0][0] == "gdb"]
        assert len(gdb_calls) == 1
        assert gdb_calls[0].kwargs["env"] == expected_env
        assert gdb_calls[0].kwargs["stderr"] == subprocess.STDOUT

    @patch("testrig.rig.subprocess.Popen")
    def test_execute_binary_receives_rocr_visible_devices(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._execute_binary("/fake/bin/test_a")

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=expected_env,
            text=True,
            bufsize=1,
        )


# ==========================================================================
# Group L: script runner
# ==========================================================================


def make_script_rig(rig_dir, **distro_spec):
    spec = {"name": "scripts", "ubuntu": {"runner": "script", "tests": ["t.py"], **distro_spec}}
    run = Rig("scripts", spec, False, TEST_UUID, rig_dir=str(rig_dir))
    run.distro = make_mock_distro("ubuntu")
    return run


class TestScriptRunnerRig:
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_setup_resolves_test_path_against_rig_dir(self, mock_get_distro, mock_mkdtemp, tmp_path):
        run = make_script_rig(tmp_path, test_path="tests")
        mock_get_distro.return_value = run.distro

        run._setup()

        assert run.binary_path == str(tmp_path / "tests")

    def test_resolves_tests_field(self, tmp_path):
        run = make_script_rig(tmp_path)
        run.binary_path = str(tmp_path)

        run._resolve_test_binaries()

        assert run.test_binaries == [str(tmp_path / "t.py")]

    def test_missing_tests_field_raises(self, tmp_path):
        spec = {"name": "scripts", "ubuntu": {"runner": "script"}}
        run = Rig("scripts", spec, False, TEST_UUID, rig_dir=str(tmp_path))
        run.distro = make_mock_distro("ubuntu")
        run.binary_path = str(tmp_path)

        with pytest.raises(Exception, match='"tests" is not specified'):
            run._resolve_test_binaries()

    @patch("testrig.rig.subprocess.Popen")
    def test_runs_with_interpreter_and_extra_args(self, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)
        script = tmp_path / "t.py"
        script.write_text("print('hi')\n")
        script.chmod(0o644)
        run = make_script_rig(tmp_path, interpreter="python3 -u")
        run.rig_spec["extra_args"] = ["--fast"]

        assert run._execute_binary(str(script)) is True

        assert mock_subproc.call_args[0][0] == ["python3", "-u", str(script), "--fast"]
        assert run.test_results[0]["command"] == ["python3", "-u", str(script), "--fast"]

    @patch("testrig.rig.subprocess.Popen")
    def test_non_executable_without_interpreter_fails(self, mock_subproc, tmp_path):
        script = tmp_path / "t.py"
        script.write_text("print('hi')\n")
        script.chmod(0o644)
        run = make_script_rig(tmp_path)

        assert run._execute_binary(str(script)) is False
        mock_subproc.assert_not_called()

    def test_verify_packages_checks_all_listed(self, tmp_path):
        run = make_script_rig(tmp_path, test_packages=["python3", "python3-numpy"])
        run.distro.check_for_installed_packages.return_value = True

        run.verify_packages()

        run.distro.check_for_installed_packages.assert_called_once_with(
            ["python3", "python3-numpy"], install_if_not_present=True
        )

    def test_verify_packages_none_required(self, tmp_path, caplog):
        run = make_script_rig(tmp_path)

        with caplog.at_level(logging.INFO):
            run.verify_packages()

        run.distro.check_for_installed_packages.assert_not_called()
        assert "no test packages required" in caplog.text

    def test_verify_debug_packages_none_required(self, tmp_path):
        run = make_script_rig(tmp_path)

        run.verify_debug_packages()

        run.distro.check_for_installed_packages.assert_not_called()

    @patch("testrig.rig.subprocess.Popen")
    def test_gather_debug_info_skipped(self, mock_subproc, tmp_path, caplog):
        run = make_script_rig(tmp_path)
        run.workdir = str(tmp_path)

        with caplog.at_level(logging.INFO):
            assert run.gather_debug_info([str(tmp_path / "t.py")]) is False

        mock_subproc.assert_not_called()
        assert "not supported" in caplog.text

    @patch("testrig.rig.subprocess.Popen")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_force_debug_not_recorded_as_debug_run(self, mock_get_distro, mock_mkdtemp, mock_subproc, tmp_path):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_script_rig(tmp_path)
        mock_get_distro.return_value = run.distro

        run.execute(force_debug=True)

        assert run.was_debug_run is False
        assert run.debug_binaries == []

    def test_unknown_runner_raises(self, tmp_path):
        run = make_script_rig(tmp_path, runner="nope")

        with pytest.raises(Exception, match='unknown runner "nope"'):
            run.verify_packages()


# ==========================================================================
# Group M: structured (junit) results
# ==========================================================================

JUNIT_PASS_FAIL_SKIP = """<testsuites><testsuite>
<testcase name="ok" time="0.1"/>
<testcase name="bad"><failure message="boom"/></testcase>
<testcase name="later"><skipped message="nope"/></testcase>
</testsuite></testsuites>"""

JUNIT_ALL_SKIP = '<testsuite><testcase name="later"><skipped/></testcase></testsuite>'


def popen_writing_junit(mock_popen, content, returncode=0):
    """Make the mocked test process write `content` to $TESTRIG_RESULTS_FILE."""

    def fake_popen(command, **kwargs):
        if content is not None:
            with open(kwargs["env"]["TESTRIG_RESULTS_FILE"], "w") as results_file:
                results_file.write(content)
        return make_popen_mock(MagicMock(), returncode=returncode)

    mock_popen.side_effect = fake_popen


def make_junit_rig(tmp_path, **kwargs):
    spec = {"name": "t", "results": "junit", **kwargs.pop("spec", {})}
    run = Rig("t", spec, False, TEST_UUID, **kwargs)
    run.workdir = str(tmp_path)
    return run


@pytest.mark.usefixtures("assume_binaries_present")
class TestJunitResults:
    @patch("testrig.rig.subprocess.Popen")
    def test_placeholder_and_env_var_point_at_results_file(self, mock_subproc, tmp_path):
        popen_writing_junit(mock_subproc, JUNIT_ALL_SKIP)
        run = make_junit_rig(tmp_path, spec={"extra_args": ["--out={results_file}"]})

        run._execute_binary("/bin/test_a")

        expected_path = str(tmp_path / "000-test_a.junit.xml")
        command = mock_subproc.call_args[0][0]
        assert command == ["/bin/test_a", f"--out={expected_path}"]
        assert mock_subproc.call_args.kwargs["env"]["TESTRIG_RESULTS_FILE"] == expected_path
        assert run.test_results[0]["results_file"] == expected_path

    @patch("testrig.rig.subprocess.Popen")
    def test_results_file_in_output_dir_when_file_output(self, mock_subproc, tmp_path):
        popen_writing_junit(mock_subproc, JUNIT_ALL_SKIP)
        output_dir = tmp_path / "out"
        output_dir.mkdir()
        run = make_junit_rig(tmp_path, output_dir=str(output_dir), file_output=True)

        run._execute_binary("/bin/test_a")

        assert (output_dir / "000-test_a.junit.xml").exists()

    @patch("testrig.rig.subprocess.Popen")
    def test_zero_exit_with_failed_case_is_warn(self, mock_subproc, tmp_path, caplog):
        popen_writing_junit(mock_subproc, JUNIT_PASS_FAIL_SKIP, returncode=0)
        run = make_junit_rig(tmp_path)

        with caplog.at_level(logging.INFO):
            assert run._execute_binary("/bin/test_a") is True

        result = run.test_results[0]
        assert result["execution_state"] == "WARN"
        assert result["results_status"] == "ok"
        assert [case.state for case in result["test_cases"]] == ["PASS", "FAIL", "SKIP"]
        assert "result: WARN (cases passed: 1, failed: 1, skipped: 1)" in caplog.text

    @patch("testrig.rig.subprocess.Popen")
    def test_nonzero_exit_is_fail(self, mock_subproc, tmp_path):
        popen_writing_junit(mock_subproc, JUNIT_PASS_FAIL_SKIP, returncode=1)
        run = make_junit_rig(tmp_path)

        assert run._execute_binary("/bin/test_a") is False
        assert run.test_results[0]["execution_state"] == "FAIL"

    @patch("testrig.rig.subprocess.Popen")
    def test_missing_results_after_crash(self, mock_subproc, tmp_path, caplog):
        popen_writing_junit(mock_subproc, None, returncode=-11)
        run = make_junit_rig(tmp_path)

        with caplog.at_level(logging.WARNING):
            run._execute_binary("/bin/test_a")

        result = run.test_results[0]
        assert result["execution_state"] == "FAIL"
        assert result["results_status"] == "missing"
        assert result["test_cases"] == []
        assert "results file was not written" in caplog.text

    @patch("testrig.rig.subprocess.Popen")
    def test_run_tests_buckets_by_state(self, mock_subproc, tmp_path):
        contents = iter([JUNIT_ALL_SKIP, JUNIT_PASS_FAIL_SKIP, None])
        returncodes = iter([0, 0, 1])

        def fake_popen(command, **kwargs):
            content = next(contents)
            if content is not None:
                with open(kwargs["env"]["TESTRIG_RESULTS_FILE"], "w") as results_file:
                    results_file.write(content)
            return make_popen_mock(MagicMock(), returncode=next(returncodes))

        mock_subproc.side_effect = fake_popen
        run = make_junit_rig(tmp_path)
        run.distro = make_mock_distro()
        run.test_binaries = ["/bin/skippy", "/bin/warny", "/bin/faily"]

        result = run.run_tests()

        assert result == run_results(skipped=["/bin/skippy"], warned=["/bin/warny"], failed=["/bin/faily"])

    @patch("testrig.rig.subprocess.Popen")
    def test_returncode_format_has_no_results_fields(self, mock_subproc):
        make_popen_mock(mock_subproc, returncode=0)
        run = make_rig()

        run._execute_binary("/bin/test_a")

        assert "test_cases" not in run.test_results[0]
        assert "TESTRIG_RESULTS_FILE" not in mock_subproc.call_args.kwargs["env"]

    def test_unknown_results_format_raises(self):
        run = make_rig(spec={"name": "t", "results": "tap"})

        with pytest.raises(Exception, match='unknown results format "tap"'):
            run.results_format

    def test_results_inside_distro_section_raises(self):
        run = make_rig(spec={"name": "t", "ubuntu": {"results": "junit"}})
        run.distro = make_mock_distro("ubuntu")

        with pytest.raises(Exception, match=r'inside \[ubuntu\] but must be a top-level key'):
            run.results_format

    @patch("testrig.rig.subprocess.Popen")
    def test_placeholder_without_junit_raises(self, mock_subproc):
        run = make_rig(spec={"name": "t", "extra_args": ["--junitxml={results_file}"]})

        with pytest.raises(Exception, match=r'\{results_file\} is used but the results format is "returncode"'):
            run._execute_binary("/bin/test_a")

        mock_subproc.assert_not_called()
