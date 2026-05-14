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

    @abstractmethod
    def get_installed_packages(self):
        raise NotImplementedError

    @abstractmethod
    def check_for_installed_packages(self, package_name, install_if_not_present=False):
        raise NotImplementedError

    @abstractmethod
    def install_packages(self, packages):
        raise NotImplementedError

    @abstractmethod
    def get_package_info(self, package_name):
        raise NotImplementedError
