# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for testrig.summary."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from testrig import summary

# Trimmed but structurally faithful excerpt of real `rocminfo` output (see
# example/trivial for a full sample) - used to exercise _gather_gpu_info's
# agent-block parsing without depending on mutable example run output.
ROCMINFO_SAMPLE_OUTPUT = """ROCk module is loaded
=====================
HSA System Attributes
=====================
Runtime Version:         1.1
*******
Agent 1
*******
  Name:                    AMD Ryzen 7 PRO 7840U w/ Radeon 780M Graphics
  Marketing Name:          AMD Ryzen 7 PRO 7840U w/ Radeon 780M Graphics
  Vendor Name:             CPU
  Device Type:             CPU
  ISA Info:
*******
Agent 2
*******
  Name:                    gfx1103
  Marketing Name:          AMD Radeon 780M Graphics
  Vendor Name:             AMD
  Device Type:             GPU
  ISA Info:
    ISA 1
      Name:                    amdgcn-amd-amdhsa--gfx1103
    ISA 2
      Name:                    amdgcn-amd-amdhsa--gfx11-generic
*******
Agent 3
*******
  Name:                    aie2
  Marketing Name:          AIE-ML
  Vendor Name:             AMD
  Device Type:             DSP
  ISA Info:
*** Done ***"""


def _load_rocminfo_output():
    return ROCMINFO_SAMPLE_OUTPUT


def make_fake_rig(**overrides):
    distro = MagicMock()
    distro.name = "fedora"
    distro.get_installed_packages.return_value = None
    distro.get_distro_family.return_value = None
    distro.get_distro_release.return_value = None
    distro.is_inbox_kernel.return_value = None

    start_time = datetime(2026, 8, 19, 17, 0, 0, tzinfo=timezone.utc)
    rig = SimpleNamespace(
        distro=distro,
        dry_run=False,
        run_result={"passed": ["/bin/test_a"], "failed": []},
        run_uuid="018f9a1c-7b3e-7c2a-9f4d-3a1b2c4d5e6f",
        start_time=start_time,
        rocminfo_output=None,
        rig_dir="/nonexistent",
        test_results=[],
        was_debug_run=False,
        debug_binaries=[],
        settings={"disable_debug": False},
    )
    for key, value in overrides.items():
        setattr(rig, key, value)
    return rig


# ==========================================================================
# _iso_duration / _iso_timestamp
# ==========================================================================


class TestIsoFormatting:
    def test_duration_seconds_only(self):
        assert summary._iso_duration(timedelta(seconds=30)) == "PT30S"

    def test_duration_minutes_and_seconds(self):
        assert summary._iso_duration(timedelta(minutes=2, seconds=15)) == "PT2M15S"

    def test_duration_hours_minutes_seconds(self):
        assert summary._iso_duration(timedelta(hours=1, minutes=4, seconds=12)) == "PT1H4M12S"

    def test_duration_zero(self):
        assert summary._iso_duration(timedelta(seconds=0)) == "PT0S"

    def test_timestamp_includes_utc_offset(self):
        dt = datetime(2026, 8, 19, 17, 0, 0, tzinfo=timezone.utc)
        assert summary._iso_timestamp(dt) == "2026-08-19T17:00:00+00:00"


# ==========================================================================
# _detect_container_type
# ==========================================================================


class TestDetectContainerType:
    @patch("testrig.summary.os.path.exists")
    def test_docker(self, mock_exists):
        mock_exists.side_effect = lambda path: path == "/.dockerenv"

        assert summary._detect_container_type() == "docker"

    @patch("testrig.summary.os.path.exists")
    def test_podman(self, mock_exists):
        mock_exists.side_effect = lambda path: path == "/run/.containerenv"

        assert summary._detect_container_type() == "podman"

    @patch("testrig.summary.open", new_callable=mock_open, read_data=b"container=lxc\x00")
    @patch("testrig.summary.os.path.exists", return_value=False)
    def test_lxc(self, mock_exists, mock_open_file):
        assert summary._detect_container_type() == "lxc"

    @patch("testrig.summary.open", side_effect=OSError)
    @patch("testrig.summary.os.path.exists", return_value=False)
    def test_none_when_not_containerized(self, mock_exists, mock_open_file):
        assert summary._detect_container_type() == "none"


# ==========================================================================
# _gather_gpu_info
# ==========================================================================


class TestGatherGpuInfo:
    def test_no_output_returns_empty_list(self):
        assert summary._gather_gpu_info(None) == []

    def test_parses_gpu_agent_from_real_rocminfo_output(self):
        gpus = summary._gather_gpu_info(_load_rocminfo_output())

        # only the GPU agent should be included, not the CPU or DSP agents
        assert len(gpus) == 1
        assert gpus[0]["marketing_name"] == "AMD Radeon 780M Graphics"
        assert gpus[0]["vendor_name"] == "AMD"
        assert gpus[0]["isa"] == "amdgcn-amd-amdhsa--gfx1103"
        # TODO: firmware_version has no known source from rocminfo output yet
        assert gpus[0]["firmware_version"] is None


# ==========================================================================
# _gather_git_info
# ==========================================================================


class TestGatherGitInfo:
    def test_non_repo_directory_returns_all_none(self, tmp_path):
        info = summary._gather_git_info(str(tmp_path))

        assert info == {"repo_uri": None, "revision": None, "is_modified": None}

    def test_clean_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

        info = summary._gather_git_info(str(tmp_path))

        assert info["revision"] is not None
        assert info["is_modified"] is False

    def test_modified_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        (tmp_path / "file.txt").write_text("hello\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / "file.txt").write_text("changed\n")

        info = summary._gather_git_info(str(tmp_path))

        assert info["is_modified"] is True


# ==========================================================================
# build_summary
# ==========================================================================


class TestBuildSummary:
    def _load_schema(self):
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "docs", "output_format.schema.json"
        )
        with open(schema_path, "r") as schema_file:
            return json.load(schema_file)

    def test_top_level_required_keys_present(self):
        required_keys = self._load_schema()["required"]
        rig = make_fake_rig()

        result = summary.build_summary(rig)

        for key in required_keys:
            assert key in result

    def test_runner_system_information_required_keys_present(self):
        required_keys = self._load_schema()["properties"]["runner_system_information"]["required"]
        rig = make_fake_rig()

        result = summary.build_summary(rig)

        for key in required_keys:
            assert key in result["runner_system_information"]

    def test_todo_distro_fields_use_placeholders_when_unimplemented(self):
        rig = make_fake_rig()

        result = summary.build_summary(rig)

        system_info = result["runner_system_information"]
        assert system_info["distro_family"] == "unknown"
        assert system_info["distro_release"] == "unknown"
        assert system_info["installed_packages"] == {}
        assert system_info["kernel"]["is_inbox_kernel"] is False
        assert system_info["distro"] == "fedora"

    def test_overall_result_pass(self):
        rig = make_fake_rig(run_result={"passed": ["a"], "failed": []})

        assert summary.build_summary(rig)["overall_result"] == "PASS"

    def test_overall_result_fail(self):
        rig = make_fake_rig(run_result={"passed": [], "failed": ["a"]})

        assert summary.build_summary(rig)["overall_result"] == "FAIL"

    def test_overall_result_unknown_for_dry_run(self):
        rig = make_fake_rig(dry_run=True, run_result={"passed": [], "failed": []})

        assert summary.build_summary(rig)["overall_result"] == "UNKNOWN"

    def test_test_information_formats_timestamps_and_duration(self):
        start = datetime(2026, 8, 19, 17, 1, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=30)
        rig = make_fake_rig(
            test_results=[
                {
                    "binary": "/bin/test_a",
                    "command": ["/bin/test_a"],
                    "execution_state": "PASS",
                    "start_time": start,
                    "end_time": end,
                    "duration": end - start,
                    "return_code": 0,
                }
            ]
        )

        result = summary.build_summary(rig)

        assert result["test_information"] == [
            {
                "binary": "/bin/test_a",
                "command": ["/bin/test_a"],
                "execution_state": "PASS",
                "start_time": "2026-08-19T17:01:00+00:00",
                "end_time": "2026-08-19T17:01:30+00:00",
                "duration": "PT30S",
                "return_code": 0,
            }
        ]


# ==========================================================================
# write_summary
# ==========================================================================


class TestWriteSummary:
    def test_writes_json_file_to_output_dir(self, tmp_path):
        output_dir = tmp_path / "run-output"
        data = {"schema_version": "1.0.0"}

        written_path = summary.write_summary(data, str(output_dir))

        assert written_path == str(output_dir / "testrig_summary.json")
        with open(written_path, "r") as summary_file:
            assert json.load(summary_file) == data

    def test_creates_output_dir_if_missing(self, tmp_path):
        output_dir = tmp_path / "nested" / "dir"

        summary.write_summary({"a": 1}, str(output_dir))

        assert (output_dir / "testrig_summary.json").exists()
