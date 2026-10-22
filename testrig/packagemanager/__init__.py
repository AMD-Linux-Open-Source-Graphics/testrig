# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os
import subprocess
from abc import ABCMeta, abstractmethod


class PackageManager(metaclass=ABCMeta):
    def __init__(self, no_root=False):
        super().__init__()
        self.no_root = no_root

    def _check_root(self):
        # check if user is root
        if not self.no_root and os.geteuid() != 0:
            raise Exception(f"running as non-root user is not supported. detected uid: {os.geteuid()}")

    def _run_command(self, command):
        process = subprocess.run(command, check=False, capture_output=True)
        return (
            process.returncode,
            process.stdout.decode("utf-8"),
            process.stderr.decode("utf-8"),
        )

    @staticmethod
    def _format_command_output(stdout, stderr):
        # both streams matter: package managers split errors across stdout/stderr
        parts = []
        if stdout.strip():
            parts.append(f"stdout:\n{stdout.strip()}")
        if stderr.strip():
            parts.append(f"stderr:\n{stderr.strip()}")
        return "\n".join(parts)

    @abstractmethod
    def is_installed(self, package_name):
        raise NotImplementedError

    @abstractmethod
    def install_packages(self, package_names):
        raise NotImplementedError

    @abstractmethod
    def get_package_info(self, package_name):
        raise NotImplementedError

    @abstractmethod
    def get_installed_packages(self):
        raise NotImplementedError
