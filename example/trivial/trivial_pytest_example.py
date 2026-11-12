# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Trivial pytest module used to exercise testrig's junit results support."""

import pytest


def test_passes():
    assert True


@pytest.mark.skip(reason="demonstrates a skipped case")
def test_skipped():
    pass
