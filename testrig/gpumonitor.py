# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Opt-in GPU usage monitoring via the amd-smi CLI.

GpuMonitor samples GPU utilization, VRAM, temperature and power draw on a
background daemon thread while a test binary runs. Monitoring is best-effort:
sampling failures never propagate out of the thread and never fail the test
run, but they are logged at WARNING and surfaced in the run summary.
"""

import json
import logging
import shutil
import subprocess
import threading
from datetime import datetime, timezone

logger = logging.getLogger("testrig.gpumonitor")

AMD_SMI = "amd-smi"
# Single-shot per interval; the monitor thread owns timing and stop control.
AMD_SMI_COMMAND = [AMD_SMI, "metric", "--usage", "--mem-usage", "--temperature", "--power", "--json"]

# amd-smi key names vary by version/ASIC/partition; try candidates in order.
_UTIL_KEYS = ("gfx_activity", "gfx", "gfx_usage", "gfx_activity_pct")
_VRAM_KEYS = ("used_vram", "vram_used", "used", "vram_usage", "gtt_used", "used_gtt")
_TEMP_KEYS = ("hotspot", "junction", "edge", "temperature")
_POWER_KEYS = ("socket_power", "average_socket_power", "current_socket_power", "power")

_METRIC_FIELDS = ("utilization_pct", "vram_used_mb", "temperature_c", "power_w")


def _numeric(node):
    """Extract a number from an amd-smi field (``{"value": n}``, raw number, or "N/A")."""
    if isinstance(node, dict):
        node = node.get("value")
    if isinstance(node, bool):
        return None
    if isinstance(node, (int, float)):
        return node
    return None


def _first(section, keys):
    if not isinstance(section, dict):
        return None
    for key in keys:
        if key in section:
            value = _numeric(section[key])
            if value is not None:
                return value
    return None


def _parse_gpu_row(row):
    gpu_id = row.get("gpu")
    if gpu_id is None:
        gpu_id = row.get("gpu_id")
    return {
        "gpu": gpu_id,
        "utilization_pct": _first(row.get("usage", {}), _UTIL_KEYS),
        "vram_used_mb": _first(row.get("mem_usage", {}), _VRAM_KEYS),
        "temperature_c": _first(row.get("temperature", {}), _TEMP_KEYS),
        "power_w": _first(row.get("power", {}), _POWER_KEYS),
    }


def parse_amd_smi_output(raw):
    """Parse amd-smi metric --json output into a list of per-GPU sample dicts."""
    data = json.loads(raw)
    if isinstance(data, dict):
        # amd-smi wraps the per-GPU list under "gpu_data".
        rows = data.get("gpu_data")
        data = rows if isinstance(rows, list) else [data]
    if not isinstance(data, list):
        return []

    gpus = []
    for row in data:
        if not isinstance(row, dict):
            continue
        parsed = _parse_gpu_row(row)
        # Non-primary XCP partition rows are almost entirely N/A; drop them.
        if all(parsed[field] is None for field in _METRIC_FIELDS):
            continue
        gpus.append(parsed)
    return gpus


def _peak(current, value):
    if value is None:
        return current
    if current is None:
        return value
    return max(current, value)


class GpuMonitor:
    """Context manager that samples GPU metrics on a background daemon thread."""

    def __init__(self, interval, sample_sink=None, binary=None):
        self.interval = interval
        # Optional open file: each sample is streamed here as a JSON line.
        self.sample_sink = sample_sink
        self.binary = binary
        self.samples = []
        self._stop = threading.Event()
        self._thread = None
        self._available = shutil.which(AMD_SMI) is not None
        self._failures = {}
        self._unavailable_reason = None
        if not self._available:
            self._unavailable_reason = f"{AMD_SMI} not found on PATH"

    def __enter__(self):
        if not self._available:
            logger.warning("GPU monitoring unavailable: %s", self._unavailable_reason)
            return self
        self._thread = threading.Thread(target=self._run, name="gpu-monitor", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        return False

    def _record_failure(self, failure_class, message):
        count = self._failures.get(failure_class, 0)
        self._failures[failure_class] = count + 1
        if count == 0:
            logger.warning("GPU monitoring: %s", message)

    def _collect_once(self):
        try:
            result = subprocess.run(AMD_SMI_COMMAND, capture_output=True, text=True)
        except OSError as exc:
            self._record_failure("exec", f"failed to run {AMD_SMI}: {exc}")
            return None
        if result.returncode != 0:
            self._record_failure("returncode", f"{AMD_SMI} exited with return code {result.returncode}")
            return None
        try:
            gpus = parse_amd_smi_output(result.stdout)
        except (ValueError, TypeError) as exc:
            self._record_failure("parse", f"could not parse {AMD_SMI} output: {exc}")
            return None
        if not gpus:
            self._record_failure("empty", f"{AMD_SMI} returned no usable GPU data")
            return None
        return gpus

    def _run(self):
        while not self._stop.is_set():
            try:
                gpus = self._collect_once()
                if gpus is not None:
                    sample = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "binary": self.binary,
                        "gpus": gpus,
                    }
                    self.samples.append(sample)
                    if self.sample_sink is not None:
                        self.sample_sink.write(json.dumps(sample) + "\n")
                        self.sample_sink.flush()
            except Exception:
                # Monitoring is secondary; it must never crash the test run.
                self._record_failure("unexpected", "unexpected error in sampler loop")
                logger.warning("GPU monitoring: unexpected error in sampler loop", exc_info=True)
            self._stop.wait(self.interval)

    def _resolve_status(self, collected):
        if not self._available:
            return "unavailable", self._unavailable_reason
        if collected == 0:
            return "unavailable", self._unavailable_reason or f"{AMD_SMI} produced no samples"
        if self._failures:
            classes = ", ".join(sorted(self._failures))
            return "degraded", f"some samples failed ({classes})"
        return "ok", None

    def aggregate(self):
        """Return per-GPU peak/avg metrics plus a monitoring status block."""
        collected = len(self.samples)
        per_gpu = {}
        order = []
        for sample in self.samples:
            for gpu in sample["gpus"]:
                gpu_id = gpu.get("gpu")
                if gpu_id not in per_gpu:
                    per_gpu[gpu_id] = {
                        "util": [],
                        "vram_used_mb_peak": None,
                        "temperature_c_peak": None,
                        "power_w_peak": None,
                    }
                    order.append(gpu_id)
                acc = per_gpu[gpu_id]
                if gpu.get("utilization_pct") is not None:
                    acc["util"].append(gpu["utilization_pct"])
                acc["vram_used_mb_peak"] = _peak(acc["vram_used_mb_peak"], gpu.get("vram_used_mb"))
                acc["temperature_c_peak"] = _peak(acc["temperature_c_peak"], gpu.get("temperature_c"))
                acc["power_w_peak"] = _peak(acc["power_w_peak"], gpu.get("power_w"))

        gpus = []
        for gpu_id in order:
            acc = per_gpu[gpu_id]
            utils = acc["util"]
            gpus.append(
                {
                    "gpu": gpu_id,
                    "utilization_pct_peak": max(utils) if utils else None,
                    "utilization_pct_avg": round(sum(utils) / len(utils), 2) if utils else None,
                    "vram_used_mb_peak": acc["vram_used_mb_peak"],
                    "temperature_c_peak": acc["temperature_c_peak"],
                    "power_w_peak": acc["power_w_peak"],
                }
            )

        status, error = self._resolve_status(collected)
        return {
            "status": status,
            "error": error,
            "samples_collected": collected,
            "interval_seconds": self.interval,
            "gpus": gpus,
        }
