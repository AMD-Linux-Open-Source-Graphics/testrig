# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import glob
import logging
import os

from testrig.packagemanager import PackageManager

logger = logging.getLogger(__name__)

# apt stores downloaded package indices here; only "lock" and "partial/" exist
# until an "apt-get update" has populated it.
APT_LISTS_DIR = "/var/lib/apt/lists"


class AptPackageManager(PackageManager):
    def _has_metadata(self):
        # presence of any "*_Packages*" index means metadata has been fetched
        return bool(glob.glob(os.path.join(APT_LISTS_DIR, "*_Packages*")))

    def _update_metadata(self):
        command = ["apt-get", "update"]
        returncode, stdout, stderr = self._run_command(command)
        if returncode != 0:
            logger.error(
                "'apt-get update' failed while refreshing package metadata\n%s",
                self._format_command_output(stdout, stderr),
            )
            raise Exception("'apt-get update' failed while refreshing package metadata")

    def is_installed(self, package_name):
        command = ["dpkg-query", "-W", "-f=${Version}", package_name]
        returncode, version, _ = self._run_command(command)
        if returncode != 0:
            return None

        return version

    def install_packages(self, package_names):
        if not self._has_metadata():
            logger.info("no apt package metadata found, running 'apt-get update'")
            self._update_metadata()

        command = ["apt-get", "install", "-y"]
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
        command = ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"]
        returncode, output, stderr = self._run_command(command)
        if returncode != 0:
            logger.warning(
                "'dpkg-query' failed while listing installed packages\n%s",
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
