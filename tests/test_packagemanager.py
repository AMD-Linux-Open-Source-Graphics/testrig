# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for testrig.packagemanager.dnf and testrig.packagemanager.apt
get_installed_packages() implementations."""

from unittest.mock import MagicMock, patch

import pytest

from testrig.packagemanager.apt import AptPackageManager
from testrig.packagemanager.dnf import DnfPackageManager

# ==========================================================================
# DnfPackageManager.get_installed_packages()
# ==========================================================================


class TestDnfGetInstalledPackages:
    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_parses_name_and_version(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"rocm-tests\t6.2.0-1\ngdb\t14.2-1\n", returncode=0)
        pm = DnfPackageManager()

        result = pm.get_installed_packages()

        assert result == {"rocm-tests": "6.2.0-1", "gdb": "14.2-1"}

    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_includes_epoch_when_set(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"somepkg\t2:1.0-3\n", returncode=0)
        pm = DnfPackageManager()

        result = pm.get_installed_packages()

        assert result == {"somepkg": "2:1.0-3"}

    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_uses_rpm_qa_with_name_version_release_queryformat(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = DnfPackageManager()

        pm.get_installed_packages()

        args = mock_subproc.call_args[0][0]
        assert args[:2] == ["rpm", "-qa"]

    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_queryformat_conditionally_includes_epoch(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = DnfPackageManager()

        pm.get_installed_packages()

        queryformat = mock_subproc.call_args[0][0][3]
        assert "EPOCH" in queryformat

    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_nonzero_returncode_returns_empty_dict(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = DnfPackageManager()

        assert pm.get_installed_packages() == {}

    @patch("testrig.packagemanager.dnf.subprocess.run")
    def test_ignores_blank_lines(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"pkg-a\t1.0\n\n", returncode=0)
        pm = DnfPackageManager()

        assert pm.get_installed_packages() == {"pkg-a": "1.0"}


# ==========================================================================
# AptPackageManager.get_installed_packages()
# ==========================================================================


class TestAptGetInstalledPackages:
    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_parses_name_and_version(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"gdb\t14.2-1\nmypkg\t1.2.3-1ubuntu1\n", returncode=0)
        pm = AptPackageManager()

        result = pm.get_installed_packages()

        assert result == {"gdb": "14.2-1", "mypkg": "1.2.3-1ubuntu1"}

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_uses_dpkg_query_w(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = AptPackageManager()

        pm.get_installed_packages()

        args = mock_subproc.call_args[0][0]
        assert args[:2] == ["dpkg-query", "-W"]

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_nonzero_returncode_returns_empty_dict(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = AptPackageManager()

        assert pm.get_installed_packages() == {}


# ==========================================================================
# AptPackageManager metadata handling in install_packages()
# ==========================================================================


class TestAptHasMetadata:
    @patch("testrig.packagemanager.apt.glob.glob")
    def test_true_when_package_index_present(self, mock_glob):
        mock_glob.return_value = ["/var/lib/apt/lists/deb.debian.org_dists_stable_main_binary-amd64_Packages"]
        pm = AptPackageManager()

        assert pm._has_metadata() is True

    @patch("testrig.packagemanager.apt.glob.glob")
    def test_false_when_no_package_index(self, mock_glob):
        mock_glob.return_value = []
        pm = AptPackageManager()

        assert pm._has_metadata() is False

    @patch("testrig.packagemanager.apt.glob.glob")
    def test_globs_apt_lists_dir_for_packages_files(self, mock_glob):
        mock_glob.return_value = []
        pm = AptPackageManager()

        pm._has_metadata()

        assert mock_glob.call_args[0][0] == "/var/lib/apt/lists/*_Packages*"


class TestAptInstallPackagesMetadata:
    @patch("testrig.packagemanager.apt.subprocess.run")
    @patch.object(AptPackageManager, "_has_metadata", return_value=False)
    def test_runs_apt_get_update_when_metadata_missing(self, mock_has_metadata, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = AptPackageManager()

        pm.install_packages(["gdb"])

        commands = [call[0][0] for call in mock_subproc.call_args_list]
        assert ["apt-get", "update"] in commands

    @patch("testrig.packagemanager.apt.subprocess.run")
    @patch.object(AptPackageManager, "_has_metadata", return_value=True)
    def test_skips_apt_get_update_when_metadata_present(self, mock_has_metadata, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = AptPackageManager()

        pm.install_packages(["gdb"])

        commands = [call[0][0] for call in mock_subproc.call_args_list]
        assert ["apt-get", "update"] not in commands

    @patch("testrig.packagemanager.apt.subprocess.run")
    @patch.object(AptPackageManager, "_has_metadata", return_value=False)
    def test_updates_metadata_before_install(self, mock_has_metadata, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = AptPackageManager()

        pm.install_packages(["gdb"])

        commands = [call[0][0] for call in mock_subproc.call_args_list]
        assert commands[0] == ["apt-get", "update"]
        assert commands[1][:2] == ["apt-get", "install"]

    @patch("testrig.packagemanager.apt.subprocess.run")
    @patch.object(AptPackageManager, "_has_metadata", return_value=False)
    def test_raises_when_apt_get_update_fails(self, mock_has_metadata, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = AptPackageManager()

        with pytest.raises(Exception, match="apt-get update"):
            pm.install_packages(["gdb"])
