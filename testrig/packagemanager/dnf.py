# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import logging

from testrig.packagemanager import PackageManager

logger = logging.getLogger(__name__)


class DnfPackageManager(PackageManager):
    def is_installed(self, package_name):
        command = ["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", package_name]
        returncode, version, _ = self._run_command(command)
        if returncode != 0:
            return None

        return version

    def install_packages(self, package_names):
        command = ["dnf", "install", "-y"]
        command.extend(package_names)
        returncode, stdout, stderr = self._run_command(command)
        if returncode != 0:
            logger.error(
                "installation of packages (%s) failed\n%s",
                " ".join(package_names),
                self._format_command_output(stdout, stderr),
            )
            raise Exception("installation of packages ({}) failed".format(" ".join(package_names)))

        logger.info("packages installed '{}".format(" ".join(package_names)))

    def get_package_info(self, package_name):
        package_version = self.is_installed(package_name)
        if package_version is None:
            raise Exception(f"package {package_name} not installed")
        return package_version

    def get_installed_packages(self):
        command = ["rpm", "-qa", "--qf", "%{NAME}\t%|EPOCH?{%{EPOCH}:}:{}|%{VERSION}-%{RELEASE}\n"]
        returncode, output, stderr = self._run_command(command)
        if returncode != 0:
            logger.warning(
                "'rpm -qa' failed while listing installed packages\n%s",
                self._format_command_output(output, stderr),
            )
            return {}

        packages = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            name, _, version = line.partition("\t")
            packages[name] = version
        return packages
