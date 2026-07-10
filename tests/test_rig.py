# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Characterization tests for testrig.rig.

These tests document actual behavior, not desired behavior. Bugs are
asserted as-is and flagged with comments.
"""

import os
import logging
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from testrig.rig import parse_rig, Rig


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def make_rig(name="testrun", spec=None, dry_run=False):
    if spec is None:
        spec = {"name": name}
    return Rig(name, spec, dry_run)


def make_mock_distro(name="ubuntu"):
    distro = MagicMock()
    distro.name = name
    return distro


def make_mock_direntry(name, is_file=True, path=None):
    entry = MagicMock()
    entry.name = name
    entry.is_file.return_value = is_file
    entry.path = path or "/fake/bin/{}".format(name)
    return entry


# ==========================================================================
# Group A: parse_rig()
# ==========================================================================


class TestParseRun:
    def test_valid_toml_returns_test_rig(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(
            b'name = "mytest"\n[ubuntu]\ntest_binary_path = "/opt/bin"\ntest_package_name = "mypkg"\n'
        )

        result = parse_rig(str(toml_file))

        assert isinstance(result, Rig)
        assert result.name == "mytest"
        assert result.rig_spec["name"] == "mytest"
        assert result.rig_spec["ubuntu"]["test_binary_path"] == "/opt/bin"
        assert result.dry_run is False

    def test_valid_toml_with_dry_run(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'name = "drytest"\n')

        result = parse_rig(str(toml_file), dry_run=True)

        assert result.dry_run is True
        assert result.name == "drytest"

    def test_passes_settings_to_rig(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'name = "settingstest"\n')
        settings = {"ROCR_VISIBLE_DEVICES": "GPU-abc"}

        result = parse_rig(str(toml_file), settings=settings)

        assert result.settings["ROCR_VISIBLE_DEVICES"] == "GPU-abc"

    def test_missing_name_field_raises(self, tmp_path):
        toml_file = tmp_path / "runtest.toml"
        toml_file.write_bytes(b'[ubuntu]\ntest_binary_path = "/opt/bin"\n')

        with pytest.raises(Exception, match='Field "name" is required'):
            parse_rig(str(toml_file))


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


class TestExecuteBinary:
    @patch("testrig.rig.subprocess.run")
    def test_pass_returns_true(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        run = make_rig()

        result = run._execute_binary("/fake/bin/test_a")

        assert result is True
        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"], check=False, stderr=subprocess.STDOUT, env=expected_env
        )

    @patch("testrig.rig.subprocess.run")
    def test_fail_returns_false(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1)
        run = make_rig()

        result = run._execute_binary("/fake/bin/test_a")

        assert result is False

    @patch("testrig.rig.subprocess.run")
    def test_extra_args_appended(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        spec = {"name": "test", "extra_args": ["--gtest_filter=Foo", "--verbose"]}
        run = make_rig(spec=spec)

        run._execute_binary("/fake/bin/test_a")

        expected_cmd = ["/fake/bin/test_a", "--gtest_filter=Foo", "--verbose"]
        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(expected_cmd, check=False, stderr=subprocess.STDOUT, env=expected_env)

    @patch("testrig.rig.subprocess.run")
    def test_sets_rocr_visible_devices_when_configured(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        run = make_rig(spec={"name": "test"})
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._execute_binary("/fake/bin/test_a")

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"],
            check=False,
            stderr=subprocess.STDOUT,
            env=expected_env,
        )


# ==========================================================================
# Group E: _scan_binaries()
# ==========================================================================


class TestScanBinaries:
    @patch("testrig.rig.os.scandir")
    def test_includes_extensionless_files(self, mock_scandir):
        mock_scandir.return_value = [
            make_mock_direntry("test_foo", is_file=True, path="/bin/test_foo"),
            make_mock_direntry("test_bar", is_file=True, path="/bin/test_bar"),
        ]
        run = make_rig()
        run.binary_path = "/bin"

        run._scan_binaries()

        assert run.test_binaries == ["/bin/test_foo", "/bin/test_bar"]

    @patch("testrig.rig.os.scandir")
    def test_excludes_files_with_extensions(self, mock_scandir):
        mock_scandir.return_value = [
            make_mock_direntry("test_foo", is_file=True, path="/bin/test_foo"),
            make_mock_direntry("spec.yaml", is_file=True, path="/bin/spec.yaml"),
            make_mock_direntry("readme.txt", is_file=True, path="/bin/readme.txt"),
        ]
        run = make_rig()
        run.binary_path = "/bin"

        run._scan_binaries()

        assert run.test_binaries == ["/bin/test_foo"]

    @patch("testrig.rig.os.scandir")
    def test_excludes_run_tests(self, mock_scandir):
        mock_scandir.return_value = [
            make_mock_direntry("test_foo", is_file=True, path="/bin/test_foo"),
            make_mock_direntry("run-tests", is_file=True, path="/bin/run-tests"),
        ]
        run = make_rig()
        run.binary_path = "/bin"

        run._scan_binaries()

        assert run.test_binaries == ["/bin/test_foo"]

    @patch("testrig.rig.os.scandir")
    def test_excludes_directories(self, mock_scandir):
        mock_scandir.return_value = [
            make_mock_direntry("test_foo", is_file=True, path="/bin/test_foo"),
            make_mock_direntry("subdir", is_file=False, path="/bin/subdir"),
        ]
        run = make_rig()
        run.binary_path = "/bin"

        run._scan_binaries()

        assert run.test_binaries == ["/bin/test_foo"]

    @patch("testrig.rig.os.scandir")
    def test_empty_directory(self, mock_scandir):
        mock_scandir.return_value = []
        run = make_rig()
        run.binary_path = "/bin"

        run._scan_binaries()

        assert run.test_binaries == []


# ==========================================================================
# Group F: run_tests()
# ==========================================================================


class TestRunTests:
    @patch("testrig.rig.subprocess.run")
    def test_all_pass(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == {"passed": ["/bin/test_a", "/bin/test_b"], "failed": []}

    @patch("testrig.rig.subprocess.run")
    def test_all_fail(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == {"passed": [], "failed": ["/bin/test_a", "/bin/test_b"]}

    @patch("testrig.rig.subprocess.run")
    def test_mixed_results(self, mock_subproc):
        mock_subproc.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1),
        ]

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a", "/bin/test_b"]

        result = run.run_tests()

        assert result == {"passed": ["/bin/test_a"], "failed": ["/bin/test_b"]}

    @patch("testrig.rig.subprocess.run")
    def test_total_tests_print_bug(self, mock_subproc, caplog):
        """BUG: 'total tests run: '.format(num_tests_run) has no {} placeholder.
        The count is silently lost."""
        mock_subproc.return_value = MagicMock(returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = ["/bin/test_a"]

        with caplog.at_level(logging.INFO):
            run.run_tests()

        assert "total tests run: 1" in caplog.text

    def test_discovers_binaries_if_none(self):
        run = make_rig()
        run.distro = make_mock_distro()
        run.binary_path = "/bin"
        run.test_binaries = None

        with patch.object(run, "_scan_binaries") as mock_discover:

            def set_binaries():
                run.test_binaries = []

            mock_discover.side_effect = set_binaries

            result = run.run_tests()
            mock_discover.assert_called_once()
            assert result == {"passed": [], "failed": []}


# ==========================================================================
# Group G: execute()
# ==========================================================================


class TestExecute:
    @patch("testrig.rig.subprocess.run")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_normal_mode_returns_results(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        mock_subproc.return_value = MagicMock(returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/opt/bin", "test_package_name": "mypkg"},
        }
        run = make_rig(spec=spec)

        with patch("testrig.rig.os.scandir") as mock_scandir:
            mock_scandir.return_value = [
                make_mock_direntry("test_a", is_file=True, path="/opt/bin/test_a"),
            ]
            result = run.execute(force_debug=False)

        assert result == {"passed": ["/opt/bin/test_a"], "failed": []}

    @patch("testrig.rig.subprocess.run")
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
        mock_subproc.return_value = MagicMock(returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {
                "test_binary_path": "/opt/bin",
                "test_package_name": "mypkg",
                "test_debug_package_names": ["mypkg-dbg"],
            },
        }
        run = make_rig(spec=spec)

        with patch("testrig.rig.os.scandir") as mock_scandir:
            mock_scandir.return_value = [
                make_mock_direntry("test_a", is_file=True, path="/opt/bin/test_a"),
            ]
            result = run.execute(force_debug=True)

        assert result == {"passed": [], "failed": []}

    @patch("testrig.rig.subprocess.run")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_disable_debug_overrides_force_debug(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        """When disable_debug=True, force_debug is ignored and tests are run."""
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        mock_subproc.return_value = MagicMock(returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/opt/bin", "test_package_name": "mypkg"},
        }
        run = make_rig(spec=spec)

        with patch("testrig.rig.os.scandir") as mock_scandir:
            mock_scandir.return_value = [
                make_mock_direntry("test_a", is_file=True, path="/opt/bin/test_a"),
            ]
            result = run.execute(force_debug=True, disable_debug=True)

        assert result == {"passed": ["/opt/bin/test_a"], "failed": []}

    @patch("testrig.rig.subprocess.run")
    @patch("testrig.rig.tempfile.mkdtemp", return_value="/tmp/fake")
    @patch("testrig.rig.get_distro")
    def test_disable_debug_runs_tests(self, mock_get_distro, mock_mkdtemp, mock_subproc):
        """When disable_debug=True and force_debug=False, tests run normally."""
        mock_distro = make_mock_distro("ubuntu")
        mock_distro.check_for_installed_packages.return_value = True
        mock_distro.get_package_info.return_value = "1.0"
        mock_get_distro.return_value = mock_distro

        mock_subproc.return_value = MagicMock(returncode=0)

        spec = {
            "name": "test",
            "ubuntu": {"test_binary_path": "/opt/bin", "test_package_name": "mypkg"},
        }
        run = make_rig(spec=spec)

        with patch("testrig.rig.os.scandir") as mock_scandir:
            mock_scandir.return_value = [
                make_mock_direntry("test_a", is_file=True, path="/opt/bin/test_a"),
            ]
            result = run.execute(force_debug=False, disable_debug=True)

        assert result == {"passed": ["/opt/bin/test_a"], "failed": []}


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
    @patch("testrig.rig.subprocess.run")
    def test_writes_gdb_batch_and_runs(self, mock_subproc, tmp_path):
        mock_subproc.return_value = MagicMock(returncode=0)

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

    @patch("testrig.rig.subprocess.run")
    def test_gdb_failure_prints_message(self, mock_subproc, tmp_path, caplog):
        mock_subproc.return_value = MagicMock(returncode=1)

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


# ==========================================================================
# Group J: prepare()
# ==========================================================================


class TestPrepare:
    @patch("testrig.rig.subprocess.run")
    def test_calls_rocminfo(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)

        run = make_rig()
        run.distro = make_mock_distro()
        run.dry_run = False

        run.prepare()

        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(["rocminfo"], check=True, stderr=subprocess.STDOUT, env=expected_env)

    @patch("testrig.rig.subprocess.run")
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


class TestRunCommand:
    @patch("testrig.rig.subprocess.run")
    def test_passes_built_env_and_redirects_stderr(self, mock_subproc):
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._run_command(["some", "command"])

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["some", "command"],
            check=False,
            stderr=subprocess.STDOUT,
            env=expected_env,
        )

    @patch("testrig.rig.subprocess.run")
    def test_forwards_check_flag(self, mock_subproc):
        run = make_rig()

        run._run_command(["some", "command"], check=True)

        expected_env = os.environ.copy()
        mock_subproc.assert_called_once_with(
            ["some", "command"],
            check=True,
            stderr=subprocess.STDOUT,
            env=expected_env,
        )


class TestSubprocessEnvPropagation:
    @patch("testrig.rig.subprocess.run")
    def test_rocminfo_receives_rocr_visible_devices(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        run = make_rig(dry_run=False)
        run.distro = make_mock_distro()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run.prepare()

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(["rocminfo"], check=True, stderr=subprocess.STDOUT, env=expected_env)

    @patch("testrig.rig.subprocess.run")
    def test_gdb_receives_rocr_visible_devices(self, mock_subproc, tmp_path):
        mock_subproc.return_value = MagicMock(returncode=0)

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

    @patch("testrig.rig.subprocess.run")
    def test_execute_binary_receives_rocr_visible_devices(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0)
        run = make_rig()
        run.settings = {"ROCR_VISIBLE_DEVICES": "GPU-123"}

        run._execute_binary("/fake/bin/test_a")

        expected_env = os.environ.copy()
        expected_env["ROCR_VISIBLE_DEVICES"] = "GPU-123"
        mock_subproc.assert_called_once_with(
            ["/fake/bin/test_a"],
            check=False,
            stderr=subprocess.STDOUT,
            env=expected_env,
        )
