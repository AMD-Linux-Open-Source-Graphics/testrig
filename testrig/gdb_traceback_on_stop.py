# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

import gdb
from pprint import pprint

"""
This is meant to be used with gdb to get a backtrace in a more automated fashion
It isn't so much a part of the testrig module but keeping it here makes it easier to find the abspath to this file
in a programmatic fashion.
"""


def stop_handler(event):
    print("event type: stop")
    print("stop signal: {}".format(event.stop_signal))
    print("stop event details:")
    pprint(event.details)

    gdb.execute("bt")


gdb.events.stop.connect(stop_handler)

print("stop handler has been imported")
