# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Characterization tests for the distro module.

Covers: get_distro(), BaseDistro, UbuntuDistro, AptPackageManager.
These tests document actual behavior, not desired behavior. Bugs are
asserted as-is and flagged with comments.
"""

import logging
from unittest.mock import MagicMock, mock_open, patch

import pytest

from testrig.distro import BaseDistro
from testrig.distro.ubuntu import UbuntuDistro
from testrig.packagemanager.apt import AptPackageManager

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def make_ubuntu_distro(distro_data=None, no_root=False):
    if distro_data is None:
        distro_data = {"id": "ubuntu", "version": "22.04"}
    return UbuntuDistro(distro_data, no_root=no_root)


def make_mock_package_manager():
    pm = MagicMock(spec=AptPackageManager)
    return pm


def fake_os_release(os_id="ubuntu", version_id="22.04", id_like=None):
    lines = [
        'NAME="Ubuntu"\n',
        f"ID={os_id}\n",
        f'VERSION_ID="{version_id}"\n',
        f'PRETTY_NAME="Ubuntu {version_id}"\n',
    ]
    if id_like is not None:
        lines.append(f'ID_LIKE="{id_like}"\n')
    return "".join(lines)


# ==========================================================================
# Group A: get_distro()
# ==========================================================================


class TestGetDistro:
    @patch("builtins.open", mock_open(read_data=fake_os_release("ubuntu", "22.04")))
    def test_returns_ubuntu_distro_on_ubuntu(self):
        from testrig.util import get_distro

        result = get_distro(no_root=True)

        assert isinstance(result, UbuntuDistro)
        assert result.name == "ubuntu"
        assert result.distro_data["id"] == "ubuntu"
        assert result.distro_data["version"] == "22.04"
        assert result.no_root is True

    @patch("builtins.open", mock_open(read_data=fake_os_release("fedora", "39")))
    def test_returns_fedora_distro_on_fedora(self):
        from testrig.distro.fedora import FedoraDistro
        from testrig.util import get_distro

        result = get_distro(no_root=True)

        assert isinstance(result, FedoraDistro)
        assert result.name == "fedora"

    @patch("builtins.open", mock_open(read_data=fake_os_release("arch", "rolling")))
    def test_raises_on_unsupported_distro(self):
        from testrig.util import get_distro

        with pytest.raises(Exception, match="Unsupported distro"):
            get_distro()

    @patch("builtins.open", mock_open(read_data="NAME=SomeOS\n"))
    def test_raises_on_missing_id_field(self):
        """When /etc/os-release has no ID= line, os_id stays None.
        The code compares None != 'ubuntu' and raises."""
        from testrig.util import get_distro

        with pytest.raises(Exception, match="Unsupported distro"):
            get_distro()

    @patch("builtins.open", mock_open(read_data=fake_os_release("ubuntu", "22.04")))
    def test_passes_no_root_false_by_default(self):
        from testrig.util import get_distro

        result = get_distro()
        assert result.no_root is False

    @patch("builtins.open", mock_open(read_data=fake_os_release("ubuntu", "22.04", id_like="debian")))
    def test_parses_id_like(self):
        from testrig.util import get_distro

        result = get_distro(no_root=True)

        assert result.distro_data["id_like"] == "debian"

    @patch("builtins.open", mock_open(read_data=fake_os_release("fedora", "39")))
    def test_id_like_defaults_to_none_when_absent(self):
        from testrig.util import get_distro

        result = get_distro(no_root=True)

        assert result.distro_data["id_like"] is None


# ==========================================================================
# Group B: BaseDistro
# ==========================================================================


class TestBaseDistro:
    def test_constructor_stores_distro_data_and_no_root(self):
        distro = make_ubuntu_distro({"id": "ubuntu", "version": "24.04"}, no_root=True)

        assert distro.distro_data == {"id": "ubuntu", "version": "24.04"}
        assert distro.no_root is True
        assert distro.package_manager is None

    def test_class_attributes(self):
        """UbuntuDistro overrides name to 'ubuntu'."""
        assert UbuntuDistro.name == "ubuntu"
        assert BaseDistro.name == "NOT_SET_FIX_ME"

    def test_cannot_instantiate_base_directly(self):
        with pytest.raises(TypeError):
            BaseDistro({"id": "test"})


# ==========================================================================
# Group C: UbuntuDistro._initialize_()
# ==========================================================================


class TestUbuntuDistroInitialize:
    def test_creates_apt_package_manager(self):
        distro = make_ubuntu_distro(no_root=True)
        assert distro.package_manager is None

        distro._init_package_manager()

        assert isinstance(distro.package_manager, AptPackageManager)

    def test_apt_package_manager_stores_no_root(self):
        """AptPackageManager inherits __init__ from PackageManager, which
        stores no_root on the instance."""
        distro = make_ubuntu_distro(no_root=True)
        distro._init_package_manager()

        assert distro.package_manager.no_root is True


# ==========================================================================
# Group D: UbuntuDistro.check_for_installed_packages()
# ==========================================================================


class TestCheckForInstalledPackages:
    def test_all_installed_returns_true(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.return_value = "1.2.3"
        distro.package_manager = pm

        result = distro.check_for_installed_packages(["pkg-a", "pkg-b"])

        assert result is True
        assert pm.is_installed.call_count == 2
        pm.install_packages.assert_not_called()

    def test_missing_package_with_install_flag(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.side_effect = ["1.2.3", ""]  # empty string is falsy
        distro.package_manager = pm

        result = distro.check_for_installed_packages(["pkg-a", "pkg-b"], install_if_not_present=True)

        assert result is True
        pm.install_packages.assert_called_once_with(["pkg-b"])

    def test_missing_package_without_install_flag_raises(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.side_effect = ["1.2.3", ""]
        distro.package_manager = pm

        with pytest.raises(Exception, match="Package pkg-b not installed"):
            distro.check_for_installed_packages(["pkg-a", "pkg-b"], install_if_not_present=False)

    def test_multiple_missing_packages_reported(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.return_value = ""  # all missing
        distro.package_manager = pm

        with pytest.raises(Exception, match="Package pkg-a pkg-b not installed"):
            distro.check_for_installed_packages(["pkg-a", "pkg-b"])

    def test_lazy_initializes_package_manager(self):
        """If package_manager is None, _initialize_ is called first."""
        distro = make_ubuntu_distro()
        assert distro.package_manager is None

        with patch.object(distro, "_init_package_manager") as mock_init:

            def set_pm():
                pm = make_mock_package_manager()
                pm.is_installed.return_value = "1.0"
                distro.package_manager = pm

            mock_init.side_effect = set_pm

            result = distro.check_for_installed_packages(["pkg-a"])

            mock_init.assert_called_once()
            assert result is True

    def test_empty_string_is_treated_as_not_installed(self):
        """AptPackageManager.is_installed returns '' (not None) for missing
        packages because _run_command uses check=False. Empty string is falsy,
        so it's treated as not installed. This happens to work correctly."""
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.return_value = ""
        distro.package_manager = pm

        with pytest.raises(Exception, match="Package pkg-a not installed"):
            distro.check_for_installed_packages(["pkg-a"])

    def test_none_is_treated_as_not_installed(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.is_installed.return_value = None
        distro.package_manager = pm

        with pytest.raises(Exception, match="Package pkg-a not installed"):
            distro.check_for_installed_packages(["pkg-a"])


# ==========================================================================
# Group E: UbuntuDistro.get_package_info()
# ==========================================================================


class TestGetPackageInfo:
    def test_returns_version(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.get_package_info.return_value = "1.2.3-1ubuntu1"
        distro.package_manager = pm

        result = distro.get_package_info("mypkg")

        assert result == "1.2.3-1ubuntu1"
        pm.get_package_info.assert_called_once_with("mypkg")

    def test_delegates_to_package_manager(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.get_package_info.side_effect = Exception("package mypkg not installed")
        distro.package_manager = pm

        with pytest.raises(Exception, match="package mypkg not installed"):
            distro.get_package_info("mypkg")


# ==========================================================================
# Group F: UbuntuDistro get_installed_packages() / install_packages() stub
# ==========================================================================


class TestUbuntuDistroStubs:
    def test_get_installed_packages_delegates_to_package_manager(self):
        distro = make_ubuntu_distro()
        pm = make_mock_package_manager()
        pm.get_installed_packages.return_value = {"pkg-a": "1.0"}
        distro.package_manager = pm

        result = distro.get_installed_packages()

        assert result == {"pkg-a": "1.0"}
        pm.get_installed_packages.assert_called_once()

    def test_get_installed_packages_lazily_initializes_package_manager(self):
        distro = make_ubuntu_distro()
        assert distro.package_manager is None

        with patch.object(distro, "_init_package_manager") as mock_init:

            def set_pm():
                pm = make_mock_package_manager()
                pm.get_installed_packages.return_value = {}
                distro.package_manager = pm

            mock_init.side_effect = set_pm

            distro.get_installed_packages()

            mock_init.assert_called_once()

    def test_install_packages_returns_none(self):
        """install_packages is a stub that does nothing (pass)."""
        distro = make_ubuntu_distro()
        result = distro.install_packages(["pkg-a"])
        assert result is None


# ==========================================================================
# Group F2: BaseDistro.get_distro_family() / get_distro_release()
# ==========================================================================


class TestGetDistroFamily:
    def test_falls_back_to_own_name_when_no_id_like(self):
        distro = make_ubuntu_distro({"id": "ubuntu", "version": "22.04"})

        assert distro.get_distro_family() == "ubuntu"

    def test_returns_id_like_when_present(self):
        distro = make_ubuntu_distro({"id": "ubuntu", "version": "22.04", "id_like": "debian"})

        assert distro.get_distro_family() == "debian"


class TestGetDistroRelease:
    def test_returns_version_from_distro_data(self):
        distro = make_ubuntu_distro({"id": "ubuntu", "version": "22.04"})

        assert distro.get_distro_release() == "22.04"


# ==========================================================================
# Group G: AptPackageManager.__init__ and _initialize_
# ==========================================================================


class TestAptPackageManagerCheckRoot:
    def test_constructor_stores_no_root(self):
        """no_root is stored as self.no_root by the PackageManager base class."""
        pm = AptPackageManager(no_root=True)
        assert pm.no_root is True

    def test_check_root_skipped_when_no_root_true(self):
        """With no_root=True, _check_root() short-circuits and does not raise."""
        pm = AptPackageManager(no_root=True)

        assert pm._check_root() is None

    @patch("testrig.packagemanager.os.geteuid", return_value=0)
    def test_initialize_with_manually_set_no_root_false_as_root(self, mock_euid):
        """If no_root is manually patched onto the instance, _initialize_
        works when running as root (euid=0)."""
        pm = AptPackageManager()
        pm.no_root = False
        # Should not raise when euid==0
        pm._check_root()
        mock_euid.assert_called_once()

    @patch("testrig.packagemanager.os.geteuid", return_value=1000)
    def test_initialize_non_root_raises(self, mock_euid):
        """When no_root=False and euid!=0, raises."""
        pm = AptPackageManager()
        pm.no_root = False

        with pytest.raises(Exception, match="running as non-root user is not supported"):
            pm._check_root()

    @patch("testrig.packagemanager.os.geteuid", return_value=1000)
    def test_initialize_with_no_root_true_skips_check(self, mock_euid):
        """When no_root=True, root check is skipped regardless of euid."""
        pm = AptPackageManager()
        pm.no_root = True
        # Should not raise
        pm._check_root()


# ==========================================================================
# Group G2: PackageManager._run_command()
# ==========================================================================


class TestRunCommand:
    @patch("testrig.packagemanager.subprocess.run")
    def test_returns_returncode_and_stdout(self, mock_subproc):
        """_run_command returns a (returncode, stdout) tuple so callers can
        check the exit status instead of relying on stdout alone."""
        mock_subproc.return_value = MagicMock(stdout=b"1.2.3", returncode=0)
        pm = AptPackageManager()

        returncode, stdout = pm._run_command(["some", "command"])

        assert returncode == 0
        assert stdout == "1.2.3"

    @patch("testrig.packagemanager.subprocess.run")
    def test_returns_nonzero_returncode(self, mock_subproc):
        """A failing command's non-zero return code is surfaced to callers."""
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = AptPackageManager()

        returncode, stdout = pm._run_command(["some", "command"])

        assert returncode == 1
        assert stdout == ""


# ==========================================================================
# Group H: AptPackageManager.is_installed()
# ==========================================================================


class TestAptIsInstalled:
    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_returns_version_string(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"1.2.3-1ubuntu1", returncode=0)
        pm = AptPackageManager()

        result = pm.is_installed("mypkg")

        assert result == "1.2.3-1ubuntu1"
        mock_subproc.assert_called_once_with(
            ["dpkg-query", "-W", "-f=${Version}", "mypkg"],
            check=False,
            capture_output=True,
        )

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_missing_package_returns_none_on_nonzero_returncode(self, mock_subproc):
        """_run_command returns the return code and is_installed checks it.
        For missing packages, dpkg-query returns a non-zero returncode, so
        is_installed returns None regardless of stdout contents."""
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = AptPackageManager()

        result = pm.is_installed("nonexistent")

        assert result is None

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_nonzero_returncode_with_stdout_still_returns_none(self, mock_subproc):
        """Even if the command writes something to stdout, a non-zero return
        code means the package is not installed, so is_installed returns None."""
        mock_subproc.return_value = MagicMock(stdout=b"some noise", returncode=1)
        pm = AptPackageManager()

        result = pm.is_installed("nonexistent")

        assert result is None

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_zero_returncode_returns_version(self, mock_subproc):
        """A zero return code means the package is installed, so the version
        string from stdout is returned."""
        mock_subproc.return_value = MagicMock(stdout=b"1.2.3-1ubuntu1", returncode=0)
        pm = AptPackageManager()

        result = pm.is_installed("mypkg")

        assert result == "1.2.3-1ubuntu1"


# ==========================================================================
# Group I: AptPackageManager.install_packages()
# ==========================================================================


class TestAptInstallPackages:
    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_successful_install(self, mock_subproc, caplog):
        mock_subproc.return_value = MagicMock(stdout=b"Installing packages...", returncode=0)
        pm = AptPackageManager()

        with caplog.at_level(logging.INFO):
            pm.install_packages(["pkg-a", "pkg-b"])

        mock_subproc.assert_called_once_with(
            ["apt-get", "install", "-y", "pkg-a", "pkg-b"],
            check=False,
            capture_output=True,
        )
        assert "packages installed 'pkg-a pkg-b" in caplog.text

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_install_command_joins_packages_as_single_arg(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=0)
        pm = AptPackageManager()

        pm.install_packages(["pkg-a", "pkg-b"])

        args = mock_subproc.call_args[0][0]
        assert args == ["apt-get", "install", "-y", "pkg-a", "pkg-b"]


# ==========================================================================
# Group J: AptPackageManager.get_package_info()
# ==========================================================================


class TestAptGetPackageInfo:
    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_returns_version(self, mock_subproc):
        mock_subproc.return_value = MagicMock(stdout=b"5.15.0-76-generic", returncode=0)
        pm = AptPackageManager()

        result = pm.get_package_info("linux-image")

        assert result == "5.15.0-76-generic"

    @patch("testrig.packagemanager.apt.subprocess.run")
    def test_raises_when_not_installed(self, mock_subproc):
        """When the package is not installed dpkg-query returns a non-zero
        return code, is_installed returns None, and get_package_info raises."""
        mock_subproc.return_value = MagicMock(stdout=b"", returncode=1)
        pm = AptPackageManager()

        with pytest.raises(Exception, match="package nonexistent not installed"):
            pm.get_package_info("nonexistent")
