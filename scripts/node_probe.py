#!/usr/bin/env python3
"""Executed through strict SSH. Output is private and consumed only by harness.py."""
import json
import os
from pathlib import Path
import platform
import subprocess


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


os_release = dict(line.split("=", 1) for line in read("/etc/os-release").splitlines() if "=" in line)
memory_kib = int(read("/proc/meminfo").split("MemTotal:")[1].split()[0])
disk = os.statvfs("/")
clock = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                       capture_output=True, text=True, timeout=10)
tun = subprocess.run(["modinfo", "tun"], capture_output=True, timeout=10)
swap_lines = read("/proc/swaps").splitlines()
checks = {
    "root_probe": os.geteuid() == 0,
    "debian_13": os_release.get("ID", "").strip('"') == "debian" and
                  os_release.get("VERSION_ID", "").strip('"') == "13",
    "amd64": platform.machine() == "x86_64",
    "cpu_budget": (os.cpu_count() or 0) >= 8,
    "memory_budget": memory_kib >= 30 * 1024 * 1024,
    "system_disk_budget": disk.f_blocks * disk.f_frsize >= 140 * 1024**3,
    "system_disk_free": disk.f_bavail * disk.f_frsize >= 50 * 1024**3,
    "ntp_synchronized": clock.returncode == 0 and clock.stdout.strip() == "yes",
    "cgroups_v2": Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
    "vmware_detected": "vmware" in read("/sys/class/dmi/id/sys_vendor").lower(),
    "swap_disabled": len(swap_lines) <= 1,
    "tun_supported": Path("/dev/net/tun").exists() or tun.returncode == 0,
}
print(json.dumps({"checks": checks, "machine_id": read("/etc/machine-id"),
                  "product_uuid": read("/sys/class/dmi/id/product_uuid")}))
