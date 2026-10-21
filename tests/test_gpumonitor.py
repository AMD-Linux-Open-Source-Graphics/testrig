# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for testrig.gpumonitor."""

import json
import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from testrig.gpumonitor import GpuMonitor, parse_amd_smi_output

SAMPLE_JSON = json.dumps(
    [
        {
            "gpu": 0,
            "usage": {"gfx_activity": {"value": 45, "unit": "%"}},
            "mem_usage": {"used_vram": {"value": 2048, "unit": "MB"}},
            "temperature": {"hotspot": {"value": 60, "unit": "C"}},
            "power": {"socket_power": {"value": 120, "unit": "W"}},
        }
    ]
)

# Real amd-smi output (26.2.0): the per-GPU list is wrapped under "gpu_data",
# and unavailable metrics are the string "N/A".
REAL_AMD_SMI_JSON = json.dumps(
    {
        "gpu_data": [
            {
                "gpu": 0,
                "usage": "N/A",
                "power": {"socket_power": "N/A", "gfx_voltage": "N/A"},
                "temperature": {"edge": {"value": 43, "unit": "C"}, "hotspot": "N/A", "mem": "N/A"},
                "mem_usage": {
                    "total_vram": {"value": 1024, "unit": "MB"},
                    "used_vram": {"value": 880, "unit": "MB"},
                    "used_gtt": {"value": 5953, "unit": "MB"},
                },
            }
        ]
    }
)


@pytest.fixture
def amd_smi_present():
    with patch("testrig.gpumonitor.shutil.which", return_value="/usr/bin/amd-smi") as which:
        yield which


class StoppingSink:
    """A sample sink that stops the monitor after its first write (deterministic)."""

    def __init__(self):
        self.lines = []
        self.monitor = None
        self.wrote = threading.Event()

    def write(self, text):
        self.lines.append(text)
        self.wrote.set()
        if self.monitor is not None:
            self.monitor._stop.set()

    def flush(self):
        pass


# ==========================================================================
# parse_amd_smi_output()
# ==========================================================================


class TestParseAmdSmiOutput:
    def test_extracts_metrics(self):
        gpus = parse_amd_smi_output(SAMPLE_JSON)

        assert gpus == [
            {
                "gpu": 0,
                "utilization_pct": 45,
                "vram_used_mb": 2048,
                "temperature_c": 60,
                "power_w": 120,
            }
        ]

    def test_coerces_na_to_none_and_drops_all_na_rows(self):
        raw = json.dumps(
            [
                {
                    "gpu": 0,
                    "usage": {"gfx_activity": "N/A"},
                    "mem_usage": {"used_vram": "N/A"},
                    "temperature": {"hotspot": "N/A"},
                    "power": {"socket_power": "N/A"},
                },
                {"gpu": 1, "usage": {"gfx_activity": {"value": 10}}},
            ]
        )

        gpus = parse_amd_smi_output(raw)

        assert len(gpus) == 1
        assert gpus[0]["gpu"] == 1
        assert gpus[0]["utilization_pct"] == 10
        assert gpus[0]["vram_used_mb"] is None

    def test_accepts_gtt_usage_for_apu(self):
        raw = json.dumps([{"gpu": 0, "mem_usage": {"gtt_used": {"value": 512}}}])

        gpus = parse_amd_smi_output(raw)

        assert gpus[0]["vram_used_mb"] == 512

    def test_accepts_single_object(self):
        raw = json.dumps({"gpu": 0, "usage": {"gfx_activity": {"value": 5}}})

        gpus = parse_amd_smi_output(raw)

        assert len(gpus) == 1
        assert gpus[0]["utilization_pct"] == 5

    def test_unwraps_gpu_data_and_coerces_na(self):
        gpus = parse_amd_smi_output(REAL_AMD_SMI_JSON)

        assert len(gpus) == 1
        assert gpus[0]["gpu"] == 0
        assert gpus[0]["utilization_pct"] is None
        assert gpus[0]["vram_used_mb"] == 880
        assert gpus[0]["temperature_c"] == 43
        assert gpus[0]["power_w"] is None

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError):
            parse_amd_smi_output("not json")


# ==========================================================================
# GpuMonitor.aggregate()
# ==========================================================================


class TestAggregate:
    def test_peak_and_average(self, amd_smi_present):
        monitor = GpuMonitor(2.0)
        for util in (40, 60, 80):
            monitor.samples.append(
                {
                    "timestamp": "t",
                    "binary": None,
                    "gpus": [
                        {
                            "gpu": 0,
                            "utilization_pct": util,
                            "vram_used_mb": 100,
                            "temperature_c": 50,
                            "power_w": 90,
                        }
                    ],
                }
            )

        aggregate = monitor.aggregate()

        gpu = aggregate["gpus"][0]
        assert gpu["utilization_pct_peak"] == 80
        assert gpu["utilization_pct_avg"] == 60.0
        assert gpu["vram_used_mb_peak"] == 100
        assert aggregate["samples_collected"] == 3
        assert aggregate["interval_seconds"] == 2.0
        assert aggregate["status"] == "ok"
        assert aggregate["error"] is None

    def test_null_metric_stays_null(self, amd_smi_present):
        monitor = GpuMonitor(1.0)
        monitor.samples.append(
            {
                "timestamp": "t",
                "binary": None,
                "gpus": [
                    {
                        "gpu": 0,
                        "utilization_pct": None,
                        "vram_used_mb": None,
                        "temperature_c": None,
                        "power_w": 50,
                    }
                ],
            }
        )

        gpu = monitor.aggregate()["gpus"][0]

        assert gpu["utilization_pct_peak"] is None
        assert gpu["utilization_pct_avg"] is None
        assert gpu["power_w_peak"] == 50

    def test_status_degraded_when_samples_and_failures(self, amd_smi_present):
        monitor = GpuMonitor(1.0)
        monitor.samples.append(
            {
                "timestamp": "t",
                "binary": None,
                "gpus": [
                    {"gpu": 0, "utilization_pct": 10, "vram_used_mb": 1, "temperature_c": 2, "power_w": 3}
                ],
            }
        )
        monitor._failures["parse"] = 1

        aggregate = monitor.aggregate()

        assert aggregate["status"] == "degraded"
        assert "parse" in aggregate["error"]

    def test_status_unavailable_when_no_samples(self, amd_smi_present):
        monitor = GpuMonitor(1.0)

        aggregate = monitor.aggregate()

        assert aggregate["status"] == "unavailable"
        assert aggregate["samples_collected"] == 0


# ==========================================================================
# GpuMonitor availability / error handling
# ==========================================================================


class TestAvailability:
    def test_unavailable_when_amd_smi_missing(self, caplog):
        with patch("testrig.gpumonitor.shutil.which", return_value=None):
            monitor = GpuMonitor(1.0)
            with caplog.at_level(logging.WARNING):
                with monitor:
                    pass

        aggregate = monitor.aggregate()
        assert aggregate["status"] == "unavailable"
        assert "not found" in aggregate["error"]
        assert monitor._thread is None
        assert any("unavailable" in record.getMessage() for record in caplog.records)

    def test_returncode_failure_is_logged_once_and_counted(self, amd_smi_present, caplog):
        with patch("testrig.gpumonitor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=2, stdout="")
            monitor = GpuMonitor(1.0)
            with caplog.at_level(logging.WARNING):
                first = monitor._collect_once()
                monitor._collect_once()

        assert first is None
        warnings = [r for r in caplog.records if "return code" in r.getMessage()]
        assert len(warnings) == 1
        assert monitor._failures["returncode"] == 2

    def test_missing_binary_does_not_raise(self, amd_smi_present):
        with patch("testrig.gpumonitor.subprocess.run", side_effect=OSError("boom")):
            monitor = GpuMonitor(1.0)
            assert monitor._collect_once() is None
            assert monitor._failures["exec"] == 1


# ==========================================================================
# GpuMonitor streaming (background thread)
# ==========================================================================


class TestStreaming:
    def test_streams_each_sample_as_a_json_line(self, amd_smi_present):
        sink = StoppingSink()
        with patch("testrig.gpumonitor.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=SAMPLE_JSON)
            monitor = GpuMonitor(0.01, sample_sink=sink, binary="/bin/test")
            sink.monitor = monitor

            monitor.__enter__()
            assert sink.wrote.wait(timeout=5)
            monitor.__exit__(None, None, None)

        assert len(sink.lines) >= 1
        first = json.loads(sink.lines[0])
        assert first["binary"] == "/bin/test"
        assert first["gpus"][0]["utilization_pct"] == 45
        assert monitor.aggregate()["status"] == "ok"
