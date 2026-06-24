# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from datetime import datetime
import os
import subprocess
import tempfile
import tomllib


from .util import get_distro

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
            print("no distro specified, assuming test binary is in $PATH", flush=True)
            self.binary_path = os.path.abspath(".")
        else:
            self.binary_path = os.path.abspath(self.rig_spec[self.distro.name]["test_binary_path"])

        # create tempdir
        self.workdir = tempfile.mkdtemp()

    def _gather_rocm_info(self):
        print("--------------------------------------------------------------------------------", flush=True)
        print("rocminfo", flush=True)
        print("--------------------------------------------------------------------------------", flush=True)
        print("", flush=True)

        if not self.dry_run:
            process = subprocess.run(["rocminfo"], check=True)
            if process.returncode != 0:
                raise Exception("rocminfo failed - returncode {}".format(process.returncode))
            print("", flush=True)

    def prepare(self):
        # check to make sure that tests package is installed
        if self.distro is None:
            self._setup()

        self._gather_rocm_info()

    # check to make sure that the system is ready to run the test
    # this is mostly checking to make sure that required packages are installed
    def verify_packages(self):
        print("--------------------------------------------------------------------------------", flush=True)
        print("checking for installed packages", flush=True)
        print("--------------------------------------------------------------------------------", flush=True)
        print("", flush=True)

        # check to make sure that tests package is installed
        if self.distro is None:
            self._setup()

        if self.distro.name not in self.rig_spec.keys():
            print("no distro information specified, not checking for any packages", flush=True)
        else:
            required_package = self.rig_spec[self.distro.name]["test_package_name"]

            do_install_missing_packages = not self.dry_run
            if self.distro.check_for_installed_packages(
                [required_package], install_if_not_present=do_install_missing_packages
            ):
                package_info = self.distro.get_package_info(required_package)
                print('required test package "{}" is installed: {}'.format(required_package, package_info), flush=True)
                print("", flush=True)

            else:
                raise Exception('required test package "{}" is not installed.'.format(required_package), flush=True)

    def _execute_binary(self, binary_path):
        run_command = [binary_path]
        if "extra_args" in self.rig_spec.keys():
            run_command.extend(self.rig_spec["extra_args"])
        print("", flush=True)

        print("", flush=True)
        print("------------------------------------------------------------", flush=True)
        print("binary: {}".format(os.path.basename(binary_path)), flush=True)
        print("------------------------------------------------------------", flush=True)
        print("running command: '{}'".format(" ".join(run_command)), flush=True)
        print("", flush=True)
        run_env = os.environ.copy()
        rocr_visible_devices = self.settings.get("ROCR_VISIBLE_DEVICES", "")
        if rocr_visible_devices:
            run_env["ROCR_VISIBLE_DEVICES"] = rocr_visible_devices

        process = subprocess.run(run_command, check=False, stderr=subprocess.STDOUT, env=run_env)
        print("", flush=True)

        if process.returncode == 0:
            print("result: PASS", flush=True)
            return True
        else:
            print("result: FAIL", flush=True)
            return False

    def _scan_binaries(self):
        self.test_binaries = []

        for testbinname in os.scandir(self.binary_path):
            # this isn't perfect but we need to avoid trying to run things like yaml files
            # for now, ignoring anything with a file extension seems like it could work even if it is a dirty hack
            if testbinname.is_file() and testbinname.name != "run-tests" and len(testbinname.name.split(".")) == 1:
                self.test_binaries.append(testbinname.path)

    def run_tests(self):
        if self.distro is None:
            self._setup()

        if self.test_binaries is None:
            self._scan_binaries()

        failed_tests = []
        passed_tests = []
        for test_binary in self.test_binaries:
            did_pass = self._execute_binary(test_binary)
            if did_pass:
                passed_tests.append(test_binary)
            else:
                failed_tests.append(test_binary)

        print("================================================================================", flush=True)
        print("RESULTS", flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)
        num_tests_run = len(passed_tests) + len(failed_tests)
        print("total tests run: {}".format(num_tests_run), flush=True)
        print("passed tests ({}/{}):".format(len(passed_tests), num_tests_run), flush=True)
        for passed_test in passed_tests:
            print("  {}".format(passed_test), flush=True)
        print("", flush=True)
        print("failed tests ({}/{}):".format(len(failed_tests), num_tests_run), flush=True)
        for failed_test in failed_tests:
            print("  {}".format(failed_test), flush=True)
        print("", flush=True)

        return {"passed": passed_tests, "failed": failed_tests}

    def verify_debug_packages(self):
        if self.distro is None:
            self._setup()

        # note - apt and/or dpkg doesn't install debug symbols for dependent packages
        # this code is going to have to get smarter (look for deps) or this will need to be a package list and it'll
        # be up to the user to specify all the debug packages
        if self.distro.name not in self.rig_spec.keys():
            print("no distro information specified, not checking for any packages", flush=True)
        else:
            required_packages = self.rig_spec[self.distro.name]["test_debug_package_names"]

            if self.distro.check_for_installed_packages(required_packages, install_if_not_present=True):
                print('required debug package "{}" is installed.'.format(" ".join(required_packages)), flush=True)
            else:
                raise Exception(
                    'required debug package "{}" was not installed.'.format(" ".join(required_packages)), flush=True
                )

    def gather_debug_info(self, failed_binaries):
        print("", flush=True)
        print("================================================================================", flush=True)
        print("gathering debug information for:", flush=True)
        for failed_binary in failed_binaries:
            print("  {}".format(failed_binary), flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)

        self.verify_debug_packages()

        # figure out path to the gdb python file we'll need
        gdb_pyfile_dir = os.path.dirname(os.path.abspath(__file__))
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
            print("", flush=True)
            print("------------------------------------------------------------", flush=True)
            print("debug binary: {}".format(os.path.basename(failed_binary)), flush=True)
            print("------------------------------------------------------------", flush=True)
            gdb_command = ["gdb", "--batch", "--command={}".format(gdb_batch_file_path), failed_binary]
            print("gdb command: {}".format(" ".join(gdb_command)), flush=True)
            print("", flush=True)
            process = subprocess.run(gdb_command, check=False, stderr=subprocess.STDOUT)
            print("", flush=True)
            if process.returncode != 0:
                print("gdb failed for {} with return code {}".format(failed_binary, process.returncode), flush=True)
                print("", flush=True)

    def execute(self, force_debug=False):
        self.start_time = datetime.now()
        print("Running test for {}".format(self.name), flush=True)

        print("================================================================================", flush=True)
        print("running check", flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)
        self._setup()
        print("identified distro as {}".format(self.distro.name), flush=True)
        self.verify_packages()

        print("", flush=True)
        print("================================================================================", flush=True)
        print("running prep", flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)

        self.prepare()

        print("", flush=True)
        print("================================================================================", flush=True)
        print("running test", flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)

        if force_debug:
            self._scan_binaries()
            self.gather_debug_info(self.test_binaries)
        else:
            run_result = self.run_tests()

        print("", flush=True)
        print("================================================================================", flush=True)
        print("run complete", flush=True)
        print("================================================================================", flush=True)
        print("", flush=True)

        runtime = datetime.now() - self.start_time
        print("Rig run started at: {}".format(self.start_time.strftime("%Y-%m-%d %H:%M:%S")), flush=True)
        print("Rig run completed at: {}".format((self.start_time + runtime).strftime("%Y-%m-%d %H:%M:%S")), flush=True)
        print("Total runtime: {}".format(runtime), flush=True)

        return run_result
