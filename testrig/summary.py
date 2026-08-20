# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

from datetime import timezone, datetime
from importlib.metadata import PackageNotFoundError, version
import grp
import json
import logging
import os
import platform
import pwd
import re
import socket
import subprocess

logger = logging.getLogger("testrig.summary")

SCHEMA_VERSION = "1.0.0"
SUMMARY_FILENAME = "testrig_summary.json"


def _testrig_version():
    try:
        return version("testrig")
    except PackageNotFoundError:
        return "unknown"


def _iso_timestamp(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _iso_duration(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration = "PT"
    if hours:
        duration += "{}H".format(hours)
    if minutes:
        duration += "{}M".format(minutes)
    duration += "{}S".format(seconds)
    return duration


def _read_proc_meminfo_kib(key):
    with open("/proc/meminfo", "r") as meminfo_file:
        for line in meminfo_file:
            if line.startswith(key + ":"):
                return int(line.split()[1])
    return None


def _format_kib_as_gib(kib):
    if kib is None:
        return None
    return "{} GiB".format(round(kib / (1024 * 1024)))


def _read_cpu_model():
    with open("/proc/cpuinfo", "r") as cpuinfo_file:
        for line in cpuinfo_file:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return None


def _detect_container_type():
    if os.path.exists("/.dockerenv"):
        return "docker"
    if os.path.exists("/run/.containerenv"):
        return "podman"
    try:
        with open("/proc/1/environ", "rb") as environ_file:
            if b"container=lxc" in environ_file.read():
                return "lxc"
    except OSError:
        pass
    return "none"


def _gather_system_info():
    return {
        "available_memory": _format_kib_as_gib(_read_proc_meminfo_kib("MemTotal")),
        "cpu": _read_cpu_model(),
        "cpu_arch": platform.machine(),
        "free_memory_at_run_start": _format_kib_as_gib(_read_proc_meminfo_kib("MemAvailable")),
        "user_account": pwd.getpwuid(os.getuid()).pw_name,
        "user_account_groups": [grp.getgrgid(gid).gr_name for gid in os.getgroups()],
        "hostname": socket.gethostname(),
        "container_type": _detect_container_type(),
    }


def _gather_kernel_info(distro):
    return {
        # TODO: distro.is_inbox_kernel() is unimplemented, defaults to False until it is
        "is_inbox_kernel": distro.is_inbox_kernel() or False,
        "version": platform.uname().release,
    }


def _parse_gpu_agent(agent_block):
    device_type_match = re.search(r"Device Type:\s*(\S+)", agent_block)
    if not device_type_match or device_type_match.group(1) != "GPU":
        return None

    marketing_match = re.search(r"Marketing Name:\s*(.+)", agent_block)
    vendor_match = re.search(r"Vendor Name:\s*(.+)", agent_block)

    isa = None
    isa_section_match = re.search(r"ISA Info:\s*\n(.*)", agent_block, re.DOTALL)
    if isa_section_match:
        isa_name_match = re.search(r"Name:\s*(\S+)", isa_section_match.group(1))
        if isa_name_match:
            isa = isa_name_match.group(1)

    return {
        "isa": isa,
        "marketing_name": marketing_match.group(1).strip() if marketing_match else None,
        "vendor_name": vendor_match.group(1).strip() if vendor_match else None,
        # TODO: rocminfo does not expose a firmware version; needs another source (e.g. amd-smi, sysfs vbios)
        "firmware_version": None,
    }


def _gather_gpu_info(rocminfo_output):
    if not rocminfo_output:
        return []

    agent_blocks = re.split(r"\*+\s*\nAgent\s+\d+\s*\n\*+\s*\n", rocminfo_output)[1:]
    return [gpu for gpu in (_parse_gpu_agent(block) for block in agent_blocks) if gpu is not None]


def _run_git(args, cwd):
    try:
        result = subprocess.run(["git", "-C", cwd] + args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _gather_git_info(rig_dir):
    revision = _run_git(["rev-parse", "HEAD"], rig_dir)
    if revision is None:
        return {"repo_uri": None, "revision": None, "is_modified": None}

    repo_uri = _run_git(["remote", "get-url", "origin"], rig_dir)
    status_output = _run_git(["status", "--porcelain"], rig_dir)
    return {
        "repo_uri": repo_uri,
        "revision": revision,
        "is_modified": bool(status_output) if status_output is not None else None,
    }


def _overall_result(rig):
    if rig.dry_run:
        return "UNKNOWN"
    if rig.run_result and rig.run_result.get("failed"):
        return "FAIL"
    return "PASS"


def build_summary(rig):
    now = datetime.now(timezone.utc)
    start_time = rig.start_time or now

    runner_system_information = {
        "kernel": _gather_kernel_info(rig.distro),
        # TODO: rig.distro.get_installed_packages() is unimplemented
        "installed_packages": rig.distro.get_installed_packages() or {},
        # TODO: rig.distro.get_distro_family() is unimplemented
        "distro_family": rig.distro.get_distro_family() or "unknown",
        "distro": rig.distro.name,
        # TODO: rig.distro.get_distro_release() is unimplemented
        "distro_release": rig.distro.get_distro_release() or "unknown",
        **_gather_system_info(),
    }

    test_information = [
        {
            "binary": test_result["binary"],
            "command": test_result["command"],
            "execution_state": test_result["execution_state"],
            "start_time": _iso_timestamp(test_result["start_time"]),
            "end_time": _iso_timestamp(test_result["end_time"]),
            "duration": _iso_duration(test_result["duration"]),
            "return_code": test_result["return_code"],
        }
        for test_result in rig.test_results
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "testrig_version": _testrig_version(),
        "run_uuid": str(rig.run_uuid),
        "start_time": _iso_timestamp(start_time),
        "end_time": _iso_timestamp(now),
        "total_runtime": _iso_duration(now - start_time),
        "is_dry_run": rig.dry_run,
        "runner_system_information": runner_system_information,
        "gpu_information": _gather_gpu_info(rig.rocminfo_output),
        "git_information": _gather_git_info(rig.rig_dir),
        "test_information": test_information,
        "debug_run_information": {"was_debug_run": rig.was_debug_run, "binaries": rig.debug_binaries},
        "testrig_options": dict(rig.settings),
        "overall_result": _overall_result(rig),
    }


def write_summary(summary_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, SUMMARY_FILENAME)
    with open(summary_path, "w") as summary_file:
        json.dump(summary_data, summary_file, indent=2)
    logger.info("wrote run summary to %s", summary_path)
    return summary_path
