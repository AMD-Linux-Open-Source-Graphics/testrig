#!/usr/bin/env python3
# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Trivial test binary used to exercise testrig's run/debug-gathering paths."""

import os
import sys
import time

import click


@click.command()
@click.option(
    "-e", "--exit-code", type=int, default=0, help="Exit with this return code (ignored if --crash-after is set)"
)
@click.option("--crash-after", type=float, default=None, help="Sleep this many seconds, then abort (SIGABRT)")
def main(exit_code, crash_after):
    click.echo("trivialtool: running")
    click.echo("trivialtool: running", err=True)

    if crash_after is not None:
        time.sleep(crash_after)
        os.abort()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
