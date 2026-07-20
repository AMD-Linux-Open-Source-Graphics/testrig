# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import os
import tomllib

# Listed in reverse order of precedence: paths later in the list override
# values from paths earlier in the list.
SETTINGS_PATHS = [
    "/etc/testrig/settings.toml",
    os.path.join(os.path.expanduser("~"), ".config", "testrig", "settings.toml"),
]

DEFAULT_SETTINGS = {
    # disable gathering of debug information (gdb runs) on failed tests
    "disable_debug": False,
    # GPU UUID(s) to expose during test execution; empty means no override
    "ROCR_VISIBLE_DEVICES": "",
    # directory containing the gdb python helper (gdb_traceback_on_stop.py)
    "gdb_pyfile_dir": "/usr/share/testrig",
}


def load_settings(paths=None):
    if paths is None:
        paths = SETTINGS_PATHS

    settings = dict(DEFAULT_SETTINGS)
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as settings_file:
            settings.update(tomllib.load(settings_file))

    return settings
