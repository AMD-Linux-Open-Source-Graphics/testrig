# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import logging
import subprocess

from testrig.packagemanager import PackageManager

logger = logging.getLogger(__name__)


class AptPackageManager(PackageManager):
    def is_installed(self, package_name):
        command = ["dpkg-query", "-W", "-f=${Version}", package_name]
        returncode, version = self._run_command(command)
        if returncode != 0:
            return None

        return version

    def install_packages(self, package_names):
        command = ["apt-get", "install", "-y"]
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

    def get_installed_packages(self):
        command = ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"]
        returncode, output = self._run_command(command)
        if returncode != 0:
            return {}

        packages = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            name, _, version = line.partition("\t")
            packages[name] = version
        return packages
