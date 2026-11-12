# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone

import tomllib

from .gpumonitor import GpuMonitor
from .results import RESULT_FORMATS, RESULT_PARSERS, RESULTS_FILE_ENV_VAR, RESULTS_FILE_PLACEHOLDER
from .runner import make_runner
from .util import get_distro

logger = logging.getLogger("testrig.rig")

REQUIRED_FIELDS = ["name"]
GPU_SAMPLES_FILENAME = "testrig_gpu_samples.jsonl"


class _LazyJsonlSink:
    """Sample sink that creates the file on first write, so no empty file is left behind."""

    def __init__(self, path):
        self._path = path
        self._handle = None

    def write(self, text):
        if self._handle is None:
            self._handle = open(self._path, "a")
        self._handle.write(text)

    def flush(self):
        if self._handle is not None:
            self._handle.flush()

    def close(self):
        if self._handle is not None:
            self._handle.close()



def parse_rig(
    inputfile_path,
    run_uuid,
    dry_run=False,
    settings=None,
    output_dir=None,
    file_output=False,
    gpu_monitoring=False,
    gpu_monitoring_interval=1.0,
):
    file_data = None

    with open(inputfile_path, "rb") as input_file:
        file_data = tomllib.load(input_file)

    for field_name in REQUIRED_FIELDS:
        if field_name not in file_data:
            raise Exception(f'Field "{field_name}" is required but not found in {inputfile_path}')
    abs_inputfile_path = os.path.abspath(inputfile_path)
    rig_dir = os.path.dirname(abs_inputfile_path)
    return Rig(
        file_data["name"],
        file_data,
        dry_run,
        run_uuid,
        settings=settings,
        output_dir=output_dir,
        file_output=file_output,
        gpu_monitoring=gpu_monitoring,
        gpu_monitoring_interval=gpu_monitoring_interval,
        rig_dir=rig_dir,
        inputfile_path=abs_inputfile_path,
    )


class Rig:
    test_binaries = None
    distro = None
    no_root = False
    workdir = None
    start_time = None

    def __init__(
        self,
        name,
        spec,
        dry_run,
        run_uuid,
        settings=None,
        output_dir=None,
        file_output=False,
        gpu_monitoring=False,
        gpu_monitoring_interval=1.0,
        rig_dir=None,
        inputfile_path=None,
    ):
        self.name = name
        self.rig_spec = spec
        self.dry_run = dry_run
        self.run_uuid = run_uuid
        self.settings = settings or {}
        self.output_dir = output_dir or os.path.abspath(".")
        self.file_output = file_output
        self.gpu_monitoring = gpu_monitoring
        self.gpu_monitoring_interval = gpu_monitoring_interval
        self.rig_dir = rig_dir or os.path.abspath(".")
        self.inputfile_path = inputfile_path
        self.test_results = []
        self.rocminfo_output = None
        self.run_result = None
        self.was_debug_run = False
        self.debug_binaries = []

        # TODO derive data from rig_spec

    @property
    def runner(self):
        distro_spec = {}
        if self.distro is not None and self.distro.name in self.rig_spec:
            distro_spec = self.rig_spec[self.distro.name]
        return make_runner(distro_spec, self.rig_dir)

    @property
    def results_format(self):
        if (
            "results" not in self.rig_spec
            and self.distro is not None
            and "results" in self.rig_spec.get(self.distro.name, {})
        ):
            raise Exception(
                f'"results" is set inside [{self.distro.name}] but must be a top-level key; '
                "move it above the first [distro] section of the rig file"
            )
        results_format = self.rig_spec.get("results", self.runner.default_results)
        if results_format not in RESULT_FORMATS:
            raise Exception(f'unknown results format "{results_format}", expected one of: {", ".join(RESULT_FORMATS)}')
        return results_format

    def _setup(self):
        self.distro = get_distro(no_root=self.no_root)

        if self.distro.name not in self.rig_spec:
            logger.info("no distro specified, assuming test binary is in $PATH")
            self.binary_path = os.path.abspath(".")
        else:
            self.binary_path = self.runner.test_dir()
        logger.info(f"results format: {self.results_format}")

        # create tempdir
        self.workdir = tempfile.mkdtemp()

    def _build_run_env(self):
        run_env = os.environ.copy()
        rocr_visible_devices = self.settings.get("ROCR_VISIBLE_DEVICES", "")
        if rocr_visible_devices:
            logger.debug("setting ROCR_VISIBLE_DEVICES to %s", rocr_visible_devices)
            run_env["ROCR_VISIBLE_DEVICES"] = rocr_visible_devices

        if self.distro is not None and self.distro.name in self.rig_spec:
            extra_env_var = self.rig_spec[self.distro.name].get("extra_env_var", {})
            for env_var_name, env_var_value in extra_env_var.items():
                logger.debug("setting %s to %s", env_var_name, env_var_value)
                run_env[env_var_name] = str(env_var_value)

        return run_env

    def _run_command(self, command, check=False, extra_env=None):
        run_env = self._build_run_env()
        run_env.update(extra_env or {})
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=run_env,
            text=True,
            bufsize=1,
        )

        output_lines = []
        try:
            for line in process.stdout:
                line = line.rstrip("\n")
                output_lines.append(line)
                logger.info(line)
        finally:
            process.stdout.close()
            process.wait()

        process.output = "\n".join(output_lines)

        if process.returncode != 0:
            logger.error(
                "command '%s' failed with returncode %s, full output:\n%s",
                " ".join(command),
                process.returncode,
                process.output,
            )
            if check:
                raise subprocess.CalledProcessError(process.returncode, command, output=process.output)

        return process

    def _gather_rocm_info(self):
        logger.info("--------------------------------------------------------------------------------")
        logger.info("rocminfo")
        logger.info("--------------------------------------------------------------------------------")

        if not self.dry_run:
            process = self._run_command(["rocminfo"], check=True)
            if process.returncode != 0:
                raise Exception(f"rocminfo failed - returncode {process.returncode}")
            self.rocminfo_output = process.output

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

        if self.distro.name not in self.rig_spec:
            logger.info("no distro information specified, not checking for any packages")
        else:
            required_packages = self.runner.required_packages()
            if not required_packages:
                logger.info("no test packages required")
                return

            do_install_missing_packages = not self.dry_run
            if self.distro.check_for_installed_packages(
                required_packages, install_if_not_present=do_install_missing_packages
            ):
                for required_package in required_packages:
                    package_info = self.distro.get_package_info(required_package)
                    logger.info(f'required test package "{required_package}" is installed: {package_info}')

            else:
                raise Exception('required test package "{}" is not installed.'.format(" ".join(required_packages)))

    def _results_file_path(self, binary_path):
        if self.file_output:
            results_dir = self.output_dir
        else:
            if self.workdir is None:
                self.workdir = tempfile.mkdtemp()
            results_dir = self.workdir
        # index prefix keeps same-named tests from different directories apart
        filename = f"{len(self.test_results):03d}-{os.path.basename(binary_path)}.junit.xml"
        return os.path.join(results_dir, filename)

    def _execute_binary(self, binary_path, sample_sink=None):
        runner = self.runner
        results_parser = RESULT_PARSERS.get(self.results_format)
        run_command = runner.build_command(binary_path)
        if "extra_args" in self.rig_spec:
            run_command.extend(self.rig_spec["extra_args"])

        results_file = None
        extra_env = None
        if results_parser is not None:
            results_file = self._results_file_path(binary_path)
            run_command = [arg.replace(RESULTS_FILE_PLACEHOLDER, results_file) for arg in run_command]
            extra_env = {RESULTS_FILE_ENV_VAR: results_file}
        elif any(RESULTS_FILE_PLACEHOLDER in arg for arg in run_command):
            raise Exception(
                f'{RESULTS_FILE_PLACEHOLDER} is used but the results format is "{self.results_format}"; '
                'set results = "junit" at the top level of the rig file'
            )

        logger.info("------------------------------------------------------------")
        logger.info(f"{runner.name}: {os.path.basename(binary_path)}")
        logger.info("------------------------------------------------------------")

        missing_reason = runner.check_runnable(binary_path)
        if missing_reason is not None:
            logger.error("%s: %s", missing_reason, binary_path)
            test_time = datetime.now(timezone.utc)
            self.test_results.append(
                {
                    "binary": binary_path,
                    "command": run_command,
                    "execution_state": "FAIL",
                    "start_time": test_time,
                    "end_time": test_time,
                    "duration": test_time - test_time,
                    "return_code": None,
                }
            )
            logger.info("result: FAIL")
            return False

        logger.info("running command: '{}'".format(" ".join(run_command)))

        gpu_monitoring = None
        test_start_time = datetime.now(timezone.utc)
        if self.gpu_monitoring and not self.dry_run:
            with GpuMonitor(
                self.gpu_monitoring_interval, sample_sink=sample_sink, binary=binary_path
            ) as monitor:
                process = self._run_command(run_command, extra_env=extra_env)
            gpu_monitoring = monitor.aggregate()
            if gpu_monitoring["status"] != "ok":
                logger.warning(
                    "GPU monitoring %s for %s: %s",
                    gpu_monitoring["status"],
                    os.path.basename(binary_path),
                    gpu_monitoring["error"],
                )
            else:
                logger.info(
                    "GPU monitoring: collected %s sample(s) for %s",
                    gpu_monitoring["samples_collected"],
                    os.path.basename(binary_path),
                )
        else:
            process = self._run_command(run_command, extra_env=extra_env)
        test_end_time = datetime.now(timezone.utc)

        results = results_parser(results_file) if results_parser is not None else None
        execution_state = runner.execution_state(process.returncode, results)
        test_result = {
            "binary": binary_path,
            "command": run_command,
            "execution_state": execution_state,
            "start_time": test_start_time,
            "end_time": test_end_time,
            "duration": test_end_time - test_start_time,
            "return_code": process.returncode,
        }
        if gpu_monitoring is not None:
            test_result["gpu_monitoring"] = gpu_monitoring
        if results is not None:
            test_result["results_file"] = results_file
            test_result["results_status"] = results.status
            test_result["results_error"] = results.error
            test_result["test_cases"] = results.cases
        self.test_results.append(test_result)

        if results is None:
            logger.info(f"result: {execution_state}")
        else:
            if results.error:
                logger.warning(results.error)
            logger.info(
                f"result: {execution_state} (cases passed: {results.count('PASS')}, "
                f"failed: {results.count('FAIL')}, skipped: {results.count('SKIP')})"
            )
        return execution_state != "FAIL"

    def _resolve_test_binaries(self):
        if self.distro.name not in self.rig_spec:
            raise Exception(f"no distro section for {self.distro.name} in rig spec, cannot resolve test binaries")

        distro_spec = self.rig_spec[self.distro.name]
        tests_field = self.runner.tests_field
        if tests_field not in distro_spec:
            raise Exception(f'required field "{tests_field}" is not specified for distro {self.distro.name}')

        self.test_binaries = [os.path.join(self.binary_path, binary_name) for binary_name in distro_spec[tests_field]]

    def _open_gpu_sample_sink(self):
        if self.dry_run or not (self.gpu_monitoring and self.file_output):
            return None
        sample_path = os.path.join(self.output_dir, GPU_SAMPLES_FILENAME)
        return _LazyJsonlSink(sample_path)

    def _log_gpu_monitoring_config(self):
        if not self.gpu_monitoring:
            logger.info("GPU monitoring: disabled")
            return
        logger.info(
            "GPU monitoring: ENABLED (sampling via amd-smi every %ss)", self.gpu_monitoring_interval
        )
        if self.dry_run:
            logger.info("GPU monitoring: skipped for this dry run")
        elif self.file_output:
            sample_path = os.path.join(self.output_dir, GPU_SAMPLES_FILENAME)
            logger.info("GPU monitoring: sample time-series will be written to %s", sample_path)
        else:
            logger.info(
                "GPU monitoring: no time-series file (file output disabled); "
                "aggregated stats still recorded in the run summary"
            )

    def _warn_if_monitoring_unusable(self):
        statuses = [
            result["gpu_monitoring"]["status"] for result in self.test_results if "gpu_monitoring" in result
        ]
        if statuses and all(status != "ok" for status in statuses):
            logger.warning("GPU monitoring was enabled but produced no usable data for any test binary")

    def run_tests(self):
        if self.distro is None:
            self._setup()

        if self.test_binaries is None:
            self._resolve_test_binaries()

        sample_sink = self._open_gpu_sample_sink()
        tests_by_state = {"passed": [], "failed": [], "warned": [], "skipped": []}
        result_keys = {"PASS": "passed", "WARN": "warned", "SKIP": "skipped"}
        try:
            for test_binary in self.test_binaries:
                self._execute_binary(test_binary, sample_sink=sample_sink)
                state = self.test_results[-1]["execution_state"]
                tests_by_state[result_keys.get(state, "failed")].append(test_binary)
        finally:
            if sample_sink is not None:
                sample_sink.close()

        if self.gpu_monitoring and not self.dry_run:
            self._warn_if_monitoring_unusable()

        logger.info("================================================================================")
        logger.info("RESULTS")
        logger.info("================================================================================")
        num_tests_run = sum(len(tests) for tests in tests_by_state.values())
        logger.info(f"total tests run: {num_tests_run}")
        for result_key, tests in tests_by_state.items():
            logger.info(f"{result_key} tests ({len(tests)}/{num_tests_run}):")
            for test in tests:
                logger.info(f"  {test}")
        return tests_by_state

    def verify_debug_packages(self):
        if self.distro is None:
            self._setup()

        # note - apt and/or dpkg doesn't install debug symbols for dependent packages
        # this code is going to have to get smarter (look for deps) or this will need to be a package list and it'll
        # be up to the user to specify all the debug packages
        if self.distro.name not in self.rig_spec:
            logger.info("no distro information specified, not checking for any packages")
        else:
            required_packages = self.runner.debug_packages()
            if not required_packages:
                logger.info("no debug packages specified, not checking for any packages")
                return

            if self.distro.check_for_installed_packages(required_packages, install_if_not_present=True):
                logger.info('required debug package "{}" is installed.'.format(" ".join(required_packages)))
            else:
                raise Exception('required debug package "{}" was not installed.'.format(" ".join(required_packages)))

    def gather_debug_info(self, failed_binaries):
        """Run failed tests under gdb; returns False if the runner doesn't support it."""
        if not self.runner.supports_gdb:
            logger.info(f'debug information gathering is not supported for "{self.runner.name}" tests, skipping')
            return False

        logger.info("================================================================================")
        logger.info("gathering debug information for:")
        for failed_binary in failed_binaries:
            logger.info(f"  {failed_binary}")
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
            gdb_batch_file.write(f"source {gdb_pyfile_path}\n")
            gdb_batch_file.write("\n")
            gdb_batch_file.write("run\n")

        # run gdb
        for failed_binary in failed_binaries:
            logger.info("------------------------------------------------------------")
            logger.info(f"debug binary: {os.path.basename(failed_binary)}")
            logger.info("------------------------------------------------------------")
            gdb_command = self.runner.debug_command(failed_binary, gdb_batch_file_path)
            logger.info("gdb command: {}".format(" ".join(gdb_command)))
            process = self._run_command(gdb_command)
            if process.returncode != 0:
                logger.warning(f"gdb failed for {failed_binary} with return code {process.returncode}")

        return True

    def execute(self, force_debug=False, disable_debug=False):
        self.start_time = datetime.now(timezone.utc)
        logger.info(f"Running test for {self.name}")
        self._log_gpu_monitoring_config()

        logger.info("================================================================================")
        logger.info("running check")
        logger.info("================================================================================")
        self._setup()
        logger.info(f"identified distro as {self.distro.name}")
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
            if self.gather_debug_info(self.test_binaries):
                self.was_debug_run = True
                self.debug_binaries = list(self.test_binaries)
            run_result = {"passed": [], "failed": [], "warned": [], "skipped": []}
        else:
            run_result = self.run_tests()
        self.run_result = run_result

        logger.info("================================================================================")
        logger.info("run complete")
        logger.info("================================================================================")

        runtime = datetime.now(timezone.utc) - self.start_time
        logger.info("Rig run started at: {}".format(self.start_time.strftime("%Y-%m-%d %H:%M:%S")))
        logger.info("Rig run completed at: {}".format((self.start_time + runtime).strftime("%Y-%m-%d %H:%M:%S")))
        logger.info(f"Total runtime: {runtime}")

        from .summary import build_summary, write_summary

        if self.file_output:
            write_summary(build_summary(self), self.output_dir)

        return run_result
