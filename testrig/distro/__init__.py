# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from abc import ABCMeta, abstractmethod


class BaseDistro(metaclass=ABCMeta):
    name = "NOT_SET_FIX_ME"
    distro_data = None
    package_manager = None

    def __init__(self, distro_data, no_root=False):
        self.distro_data = distro_data
        self.package_manager = None
        self.no_root = no_root

    @abstractmethod
    def _init_package_manager(self):
        raise NotImplementedError

    def get_installed_packages(self):
        if self.package_manager is None:
            self._init_package_manager()
        return self.package_manager.get_installed_packages()

    @abstractmethod
    def check_for_installed_packages(self, package_name, install_if_not_present=False):
        raise NotImplementedError

    @abstractmethod
    def install_packages(self, packages):
        raise NotImplementedError

    @abstractmethod
    def get_package_info(self, package_name):
        raise NotImplementedError

    # ID_LIKE (see /etc/os-release) names the broader distro family; falls back to
    # this distro's own name for distros that are themselves the family base
    def get_distro_family(self):
        return self.distro_data.get("id_like") or self.name

    def get_distro_release(self):
        return self.distro_data.get("version")
