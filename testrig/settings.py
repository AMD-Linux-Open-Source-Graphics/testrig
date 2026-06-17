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
