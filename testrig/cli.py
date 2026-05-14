# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os
from pprint import pprint
import sys

import click

from .rig import parse_rig


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
@click.pass_context
def cli(ctx, run_directory, filename, debug, no_root, dry_run):
    ctx.ensure_object(dict)
    ctx.obj["run_directory"] = run_directory
    ctx.obj["filename"] = filename
    ctx.obj["debug"] = debug
    ctx.obj["no_root"] = no_root
    ctx.obj["dry_run"] = dry_run

    input_path = os.path.abspath(os.path.join(run_directory, filename))
    if not os.path.exists(input_path):
        raise Exception("Input file not found: {}".format(input_path))

    ctx.obj["input_path"] = input_path


@cli.command("run")
@click.option(
    "--no-debug", is_flag=True, default=False, help="Do not attempt to gather debug information on failed tests"
)
@click.pass_context
def run_test(ctx, no_debug):

    print("Running test: {}".format(ctx.obj["filename"]))
    rig = parse_rig(ctx.obj["input_path"], dry_run=ctx.obj["dry_run"])
    rig.no_root = ctx.obj["no_root"]

    pprint(rig.config)

    results = rig.execute(force_debug=ctx.obj["debug"])

    if len(results["failed"]) > 0:
        if not no_debug:
            rig.gather_debug_info(results["failed"])

        print("FAILED TESTS DETECTED: exiting with return code 1")
        sys.exit(1)


@cli.command("check")
@click.option("--ignore-debug-packages", is_flag=True, default=False, help="Ignore missing debug packages")
@click.option("--ignore-test-packages", is_flag=True, default=False, help="Ignore missing test packages")
@click.pass_context
def check_install(ctx, ignore_debug_packages, ignore_test_packages):
    print("running install check for {}".format(ctx.obj["input_path"]))
    rig = parse_rig(ctx.obj["input_path"])
    rig.no_root = ctx.obj["no_root"]

    if not ignore_test_packages:
        rig.verify_packages()

    if not ignore_debug_packages:
        rig.verify_debug_packages()


if __name__ == "__main__":
    cli()
