# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
import logging
import os
import subprocess
import tempfile
import tomllib


from .util import get_distro

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["name"]


def parse_rig(inputfile_path, dry_run=False, settings=None):
    file_data = None

    with open(inputfile_path, "rb") as input_file:
        file_data = tomllib.load(input_file)

    for field_name in REQUIRED_FIELDS:
        if field_name not in file_data:
            raise Exception('Field "{}" is required but not found in {}'.format(field_name, inputfile_path))
    return Rig(file_data["name"], file_data, dry_run, settings=settings)


class Rig:
    test_binaries = None
    distro = None
    no_root = False
    workdir = None
    start_time = None

    def __init__(self, name, spec, dry_run, settings=None):
        self.name = name
        self.rig_spec = spec
        self.dry_run = dry_run
        self.settings = settings or {}

        # TODO derive data from rig_spec

    def _setup(self):
        self.distro = get_distro(no_root=self.no_root)

        if self.distro.name not in self.rig_spec.keys():
            logger.info("no distro specified, assuming test binary is in $PATH")
            self.binary_path = os.path.abspath(".")
        else:
            self.binary_path = os.path.abspath(self.rig_spec[self.distro.name]["test_binary_path"])

        # create tempdir
        self.workdir = tempfile.mkdtemp()

    def _build_run_env(self):
        run_env = os.environ.copy()
        rocr_visible_devices = self.settings.get("ROCR_VISIBLE_DEVICES", "")
        if rocr_visible_devices:
            logger.debug("setting ROCR_VISIBLE_DEVICES to %s", rocr_visible_devices)
            run_env["ROCR_VISIBLE_DEVICES"] = rocr_visible_devices

        if self.distro is not None and self.distro.name in self.rig_spec.keys():
            extra_env_var = self.rig_spec[self.distro.name].get("extra_env_var", {})
            for env_var_name, env_var_value in extra_env_var.items():
                logger.debug("setting %s to %s", env_var_name, env_var_value)
                run_env[env_var_name] = str(env_var_value)

        return run_env

    def _run_command(self, command, check=False):
        return subprocess.run(command, check=check, stderr=subprocess.STDOUT, env=self._build_run_env())

    def _gather_rocm_info(self):
        logger.info("--------------------------------------------------------------------------------")
        logger.info("rocminfo")
        logger.info("--------------------------------------------------------------------------------")

        if not self.dry_run:
            process = self._run_command(["rocminfo"], check=True)
            if process.returncode != 0:
                raise Exception("rocminfo failed - returncode {}".format(process.returncode))

    def prepare(self):
        # check to make sure that tests package is installed
        if self.distro is None:
            self._setup()

        self._gather_rocm_info()

    # check to make sure that the system is ready to run the test
    # this is mostly checking to make sure that required packages are installed
    def verify_packages(self):
        logger.info("--------------------------------------------------------------------------------")
        logger.info("checking for installed packages")
        logger.info("--------------------------------------------------------------------------------")

        # check to make sure that tests package is installed
        if self.distro is None:
            self._setup()

        if self.distro.name not in self.rig_spec.keys():
            logger.info("no distro information specified, not checking for any packages")
        else:
            required_package = self.rig_spec[self.distro.name]["test_package_name"]

            do_install_missing_packages = not self.dry_run
            if self.distro.check_for_installed_packages(
                [required_package], install_if_not_present=do_install_missing_packages
            ):
                package_info = self.distro.get_package_info(required_package)
                logger.info('required test package "{}" is installed: {}'.format(required_package, package_info))

            else:
                raise Exception('required test package "{}" is not installed.'.format(required_package))

    def _execute_binary(self, binary_path):
        run_command = [binary_path]
        if "extra_args" in self.rig_spec.keys():
            run_command.extend(self.rig_spec["extra_args"])

        logger.info("------------------------------------------------------------")
        logger.info("binary: {}".format(os.path.basename(binary_path)))
        logger.info("------------------------------------------------------------")
        logger.info("running command: '{}'".format(" ".join(run_command)))

        process = self._run_command(run_command)

        if process.returncode == 0:
            logger.info("result: PASS")
            return True
        else:
            logger.info("result: FAIL")
            return False

    def _resolve_test_binaries(self):
        if self.distro.name not in self.rig_spec.keys():
            raise Exception(
                "no distro section for {} in rig spec, cannot resolve test binaries".format(self.distro.name)
            )

        distro_spec = self.rig_spec[self.distro.name]
        if "test_binaries" not in distro_spec:
            raise Exception('required field "test_binaries" is not specified for distro {}'.format(self.distro.name))

        self.test_binaries = [
            os.path.join(self.binary_path, binary_name) for binary_name in distro_spec["test_binaries"]
        ]

    def run_tests(self):
        if self.distro is None:
            self._setup()

        if self.test_binaries is None:
            self._resolve_test_binaries()

        failed_tests = []
        passed_tests = []
        for test_binary in self.test_binaries:
            did_pass = self._execute_binary(test_binary)
            if did_pass:
                passed_tests.append(test_binary)
            else:
                failed_tests.append(test_binary)

        logger.info("================================================================================")
        logger.info("RESULTS")
        logger.info("================================================================================")
        num_tests_run = len(passed_tests) + len(failed_tests)
        logger.info("total tests run: {}".format(num_tests_run))
        logger.info("passed tests ({}/{}):".format(len(passed_tests), num_tests_run))
        for passed_test in passed_tests:
            logger.info("  {}".format(passed_test))
        logger.info("failed tests ({}/{}):".format(len(failed_tests), num_tests_run))
        for failed_test in failed_tests:
            logger.info("  {}".format(failed_test))
        return {"passed": passed_tests, "failed": failed_tests}

    def verify_debug_packages(self):
        if self.distro is None:
            self._setup()

        # note - apt and/or dpkg doesn't install debug symbols for dependent packages
        # this code is going to have to get smarter (look for deps) or this will need to be a package list and it'll
        # be up to the user to specify all the debug packages
        if self.distro.name not in self.rig_spec.keys():
            logger.info("no distro information specified, not checking for any packages")
        else:
            required_packages = self.rig_spec[self.distro.name]["test_debug_package_names"]

            if self.distro.check_for_installed_packages(required_packages, install_if_not_present=True):
                logger.info('required debug package "{}" is installed.'.format(" ".join(required_packages)))
            else:
                raise Exception('required debug package "{}" was not installed.'.format(" ".join(required_packages)))

    def gather_debug_info(self, failed_binaries):
        logger.info("================================================================================")
        logger.info("gathering debug information for:")
        for failed_binary in failed_binaries:
            logger.info("  {}".format(failed_binary))
        logger.info("================================================================================")

        self.verify_debug_packages()

        # figure out path to the gdb python file we'll need
        gdb_pyfile_dir = self.settings.get("gdb_pyfile_dir", "/usr/share/testrig")
        gdb_pyfile_path = os.path.join(gdb_pyfile_dir, "gdb_traceback_on_stop.py")

        # create gdb batch file
        gdb_batch_file_path = os.path.join(self.workdir, "run_debug.gdb")
        with open(gdb_batch_file_path, "w+") as gdb_batch_file:
            gdb_batch_file.write("# gdb batch file created by testrig on {}\n".format("%Y%m%d-%H%M%S"))
            gdb_batch_file.write("\n")
            gdb_batch_file.write("source {}\n".format(gdb_pyfile_path))
            gdb_batch_file.write("\n")
            gdb_batch_file.write("run\n")

        # run gdb
        for failed_binary in failed_binaries:
            logger.info("------------------------------------------------------------")
            logger.info("debug binary: {}".format(os.path.basename(failed_binary)))
            logger.info("------------------------------------------------------------")
            gdb_command = ["gdb", "--batch", "--command={}".format(gdb_batch_file_path), failed_binary]
            logger.info("gdb command: {}".format(" ".join(gdb_command)))
            process = self._run_command(gdb_command)
            if process.returncode != 0:
                logger.warning("gdb failed for {} with return code {}".format(failed_binary, process.returncode))

    def execute(self, force_debug=False, disable_debug=False):
        self.start_time = datetime.now()
        logger.info("Running test for {}".format(self.name))

        logger.info("================================================================================")
        logger.info("running check")
        logger.info("================================================================================")
        self._setup()
        logger.info("identified distro as {}".format(self.distro.name))
        self.verify_packages()

        logger.info("================================================================================")
        logger.info("running prep")
        logger.info("================================================================================")

        self.prepare()

        logger.info("================================================================================")
        logger.info("running test")
        logger.info("================================================================================")

        if force_debug and disable_debug:
            logger.info("debug runs are disabled by global settings, ignoring --debug")

        if force_debug and not disable_debug:
            self._resolve_test_binaries()
            self.gather_debug_info(self.test_binaries)
            run_result = {"passed": [], "failed": []}
        else:
            run_result = self.run_tests()

        logger.info("================================================================================")
        logger.info("run complete")
        logger.info("================================================================================")

        runtime = datetime.now() - self.start_time
        logger.info("Rig run started at: {}".format(self.start_time.strftime("%Y-%m-%d %H:%M:%S")))
        logger.info("Rig run completed at: {}".format((self.start_time + runtime).strftime("%Y-%m-%d %H:%M:%S")))
        logger.info("Total runtime: {}".format(runtime))

        return run_result
