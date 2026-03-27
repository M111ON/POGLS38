from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Dict


def _format_bytes_gib(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "unknown"
    gib = num_bytes / (1024 ** 3)
    return f"{gib:.1f} GiB"


def _memory_bytes() -> int:
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullTotalPhys)
        except Exception:
            return 0
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except Exception:
        pass
    try:
        with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except Exception:
        pass
    return 0


def _gpu_summary() -> str:
    if not shutil.which("nvidia-smi"):
        return "none detected"
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        ).strip()
        if not out:
            return "none detected"
        first = out.splitlines()[0]
        return first
    except Exception:
        return "present (query failed)"


def collect_system_info() -> Dict[str, str]:
    cpu_count = os.cpu_count() or 0
    uname = platform.uname()
    return {
        "hostname": platform.node() or "unknown",
        "os": f"{uname.system} {uname.release}".strip(),
        "machine": uname.machine or platform.machine() or "unknown",
        "cpu": platform.processor() or uname.processor or uname.machine or "unknown",
        "cpu_cores": str(cpu_count),
        "memory": _format_bytes_gib(_memory_bytes()),
        "python": platform.python_version(),
        "gpu": _gpu_summary(),
    }
