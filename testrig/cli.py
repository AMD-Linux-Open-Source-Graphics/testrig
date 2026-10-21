# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import datetime
import logging
import os
import sys
import uuid
from pprint import pformat

import click

from .rig import parse_rig
from .settings import load_settings

logger = logging.getLogger("testrig")


@click.group()
@click.option(
    "-r",
    "--run_directory",
    type=click.Path(dir_okay=True, exists=True),
    default=".",
    help="Directory to run the test from",
)
@click.option("-f", "--filename", type=str, default="runtest.toml", help="Name of the test configuration file")
@click.option("-d", "--debug", is_flag=True, default=False, help="Enable debug mode")
@click.option("--no-root", is_flag=True, default=False, help="Do not run as root")
@click.option("--dry-run", is_flag=True, default=False, help="Perform a dry run without executing tests")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable verbose (debug) logging")
@click.option(
    "--output-dir",
    type=click.Path(dir_okay=True),
    default=None,
    help="Base directory for storing output files. Overrides the output_dir setting; "
    "if unset, the setting (default: ./testrig-logs) is used",
)
@click.option(
    "--file-output/--no-file-output",
    "file_output",
    default=None,
    help="Enable/disable writing output files to disk. Overrides the enable_file_output setting; "
    "if unset, the setting (default: disabled) is used",
)
@click.option(
    "--gpu-monitoring/--no-gpu-monitoring",
    "gpu_monitoring",
    default=None,
    help="Enable/disable sampling GPU usage (via amd-smi) while tests run. Overrides the "
    "enable_gpu_monitoring setting; if unset, the setting (default: disabled) is used",
)
@click.pass_context
def cli(ctx, run_directory, filename, debug, no_root, dry_run, verbose, output_dir, file_output, gpu_monitoring):
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=logging.DEBUG if verbose else logging.INFO,
    )

    ctx.ensure_object(dict)
    ctx.obj["run_directory"] = run_directory
    ctx.obj["filename"] = filename
    ctx.obj["debug"] = debug
    ctx.obj["no_root"] = no_root
    ctx.obj["dry_run"] = dry_run
    ctx.obj["settings"] = load_settings()
    ctx.obj["output_dir"] = resolve_output_dir(output_dir, ctx.obj["settings"])
    if file_output is None:
        file_output = ctx.obj["settings"]["enable_file_output"]
    ctx.obj["file_output"] = file_output
    if gpu_monitoring is None:
        gpu_monitoring = ctx.obj["settings"]["enable_gpu_monitoring"]
    ctx.obj["gpu_monitoring"] = gpu_monitoring
    ctx.obj["gpu_monitoring_interval"] = ctx.obj["settings"]["gpu_monitoring_interval"]


def resolve_input_path(ctx):
    input_path = os.path.abspath(os.path.join(ctx.obj["run_directory"], ctx.obj["filename"]))
    if not os.path.exists(input_path):
        raise click.FileError(input_path, hint="input file not found")
    return input_path


def resolve_output_dir(output_dir, settings):
    if output_dir is None:
        output_dir = settings["output_dir"]
    return os.path.abspath(output_dir)


def resolve_run_output_dir(base_dir, now=None):
    if not os.path.exists(base_dir):
        return base_dir
    # base_dir is taken, so fall back to a local-time timestamped sibling
    timestamp = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M")
    candidate = f"{base_dir}-{timestamp}"
    suffix = 1
    while os.path.exists(candidate):
        candidate = f"{base_dir}-{timestamp}-{suffix}"
        suffix += 1
    return candidate


@cli.command("run")
@click.option(
    "--no-debug", is_flag=True, default=False, help="Do not attempt to gather debug information on failed tests"
)
@click.pass_context
def run_test(ctx, no_debug):

    run_uuid = uuid.uuid7()

    run_output_dir = None
    if ctx.obj["file_output"]:
        # create directory for output for this run
        run_output_dir = resolve_run_output_dir(ctx.obj["output_dir"])
        os.makedirs(run_output_dir, exist_ok=True)
        ctx.obj["run_output_dir"] = run_output_dir
        logger.info(f"Output directory for this run: {run_output_dir}")
        filelog_handler = logging.FileHandler(os.path.join(run_output_dir, "testrig.log"))
        filelog_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z")
        )
        logger.addHandler(filelog_handler)

    input_path = resolve_input_path(ctx)
    logger.info("Running test: {}".format(ctx.obj["filename"]))
    rig = parse_rig(
        input_path,
        run_uuid,
        dry_run=ctx.obj["dry_run"],
        settings=ctx.obj["settings"],
        output_dir=run_output_dir,
        file_output=ctx.obj["file_output"],
        gpu_monitoring=ctx.obj["gpu_monitoring"],
        gpu_monitoring_interval=ctx.obj["gpu_monitoring_interval"],
    )
    rig.no_root = ctx.obj["no_root"]

    logger.debug(pformat(rig.rig_spec))

    disable_debug = ctx.obj["settings"]["disable_debug"]
    logger.debug(f"disable_debug: {disable_debug}")

    results = rig.execute(force_debug=ctx.obj["debug"], disable_debug=disable_debug)

    if len(results["failed"]) > 0:
        if not no_debug and not disable_debug:
            rig.gather_debug_info(results["failed"])

        logger.error("FAILED TESTS DETECTED: exiting with return code 1")
        sys.exit(1)


@cli.command("check")
@click.option("--ignore-debug-packages", is_flag=True, default=False, help="Ignore missing debug packages")
@click.option("--ignore-test-packages", is_flag=True, default=False, help="Ignore missing test packages")
@click.pass_context
def check_install(ctx, ignore_debug_packages, ignore_test_packages):
    input_path = resolve_input_path(ctx)
    logger.info("running install check for {}".format(input_path))
    rig = parse_rig(input_path, uuid.uuid7(), settings=ctx.obj["settings"])
    rig.no_root = ctx.obj["no_root"]

    if not ignore_test_packages:
        rig.verify_packages()

    if not ignore_debug_packages:
        rig.verify_debug_packages()


if __name__ == "__main__":
    cli()
