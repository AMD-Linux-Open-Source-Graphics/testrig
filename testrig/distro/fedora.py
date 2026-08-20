# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from . import BaseDistro
from ..packagemanager.dnf import DnfPackageManager


class FedoraDistro(BaseDistro):
    name = "fedora"

    def _init_package_manager(self):
        self.package_manager = DnfPackageManager(self.no_root)

    # TODO: list all installed system packages with versions for run summary output
    def get_installed_packages(self):
        pass

    def check_for_installed_packages(self, package_names, install_if_not_present=False):
        if self.package_manager is None:
            self._init_package_manager()

        to_install = []
        is_installed = []
        for package_name in package_names:
            if self.package_manager.is_installed(package_name):
                is_installed.append(package_name)
            else:
                to_install.append(package_name)

        if len(to_install) == 0:
            return True

        if install_if_not_present:
            self.package_manager.install_packages(to_install)
            return True

        raise Exception("Package {} not installed".format(" ".join(to_install)))

    def install_packages(self, packages):
        pass

    def get_package_info(self, package_name):
        return self.package_manager.get_package_info(package_name)

    # TODO: return distro family (e.g. "fedora") for run summary output
    def get_distro_family(self):
        pass

    # TODO: return distro release (e.g. "45") for run summary output
    def get_distro_release(self):
        pass

    # TODO: determine whether the running kernel is the distro-provided kernel
    def is_inbox_kernel(self):
        pass
