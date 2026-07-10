# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import logging
import subprocess

from testrig.packagemanager import PackageManager

logger = logging.getLogger(__name__)


class DnfPackageManager(PackageManager):
    def is_installed(self, package_name):
        command = ["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", package_name]
        try:
            version = self._run_command(command)
        except subprocess.CalledProcessError:
            return None

        return version

    def install_packages(self, package_names):
        command = ["dnf", "install", "-y"]
        command.extend(package_names)
        try:
            self._run_command(command)
        except subprocess.CalledProcessError as e:
            logger.error("installation of packages ({}) failed".format(" ".join(package_names)))
            raise e

        logger.info("packages installed '{}".format(" ".join(package_names)))

    def get_package_info(self, package_name):
        package_version = self.is_installed(package_name)
        if package_version is None:
            raise Exception("package {} not installed".format(package_name))
        return package_version
