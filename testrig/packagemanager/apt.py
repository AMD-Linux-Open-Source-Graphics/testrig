# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os
import subprocess


class AptPackageManager:
    def __init__(self, no_root=False):
        super().__init__()

    def _check_root(self):
        # check if user is root
        if not self.no_root and os.geteuid() != 0:
            raise Exception("running as non-root user is not supported. detected uid: {}".format(os.geteuid()))

    def _run_command(self, command):
        process = subprocess.run(command, check=False, capture_output=True)
        return process.stdout.decode("utf-8")

    def is_installed(self, package_name):
        command = ["dpkg-query", "-W", "-f=${Version}", package_name]
        try:
            version = self._run_command(command)
        except subprocess.CalledProcessError:
            return None

        return version

    def install_packages(self, package_names):
        command = ["apt-get", "install", "-y"]
        command.extend(package_names)
        try:
            self._run_command(command)
        except subprocess.CalledProcessError as e:
            print("installation of packages ({}) failed".format(" ".join(package_names)))
            raise e

        print("packages installed '{}".format(" ".join(package_names)))

    def get_package_info(self, package_name):
        package_version = self.is_installed(package_name)
        if package_version is None:
            raise Exception("package {} not installed".format(package_name))
        return package_version
