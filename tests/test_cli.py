# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for testrig.cli."""

import datetime
import os

from testrig.cli import resolve_run_output_dir


class TestResolveRunOutputDir:
    def test_returns_base_dir_when_missing(self, tmp_path):
        base = str(tmp_path / "testrig-logs")

        assert resolve_run_output_dir(base) == base

    def test_returns_timestamped_sibling_when_base_exists(self, tmp_path):
        base = tmp_path / "testrig-logs"
        base.mkdir()
        now = datetime.datetime(2026, 10, 26, 14, 5)

        result = resolve_run_output_dir(str(base), now=now)

        assert result == str(tmp_path / "testrig-logs-20261026_1405")

    def test_appends_counter_on_same_minute_collision(self, tmp_path):
        base = tmp_path / "testrig-logs"
        base.mkdir()
        now = datetime.datetime(2026, 10, 26, 14, 5)
        (tmp_path / "testrig-logs-20261026_1405").mkdir()

        result = resolve_run_output_dir(str(base), now=now)

        assert result == str(tmp_path / "testrig-logs-20261026_1405-1")

    def test_increments_counter_until_free(self, tmp_path):
        base = tmp_path / "testrig-logs"
        base.mkdir()
        now = datetime.datetime(2026, 10, 26, 14, 5)
        (tmp_path / "testrig-logs-20261026_1405").mkdir()
        (tmp_path / "testrig-logs-20261026_1405-1").mkdir()

        result = resolve_run_output_dir(str(base), now=now)

        assert result == str(tmp_path / "testrig-logs-20261026_1405-2")

    def test_resolved_dir_does_not_contain_uuid(self, tmp_path):
        base = tmp_path / "testrig-logs"
        base.mkdir()
        now = datetime.datetime(2026, 10, 26, 14, 5)

        result = resolve_run_output_dir(str(base), now=now)

        assert os.path.basename(result).startswith("testrig-logs-")
