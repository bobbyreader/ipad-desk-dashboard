"""Cross-platform host telemetry (macOS, Windows, Linux) using Python stdlib only."""
import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading
import time

_WIN_CPU_LOCK = threading.Lock()
_WIN_PREV_TIMES = None


def mac_memory_status() -> dict:
    """Derive macOS memory usage from vm_stat and hw.memsize."""
    empty = {"percent": None, "used_gb": None, "total_gb": None}
    try:
        total_b = int(subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3, check=False,
        ).stdout.strip())
        text = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=3, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return empty
    page = 4096
    counts = {}
    for line in text.splitlines():
        if "page size of" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                page = int(digits)
            continue
        name, _, value = line.partition(":")
        value = value.strip().rstrip(".")
        if value.isdigit():
            counts[name.strip().lower()] = int(value)
    used_pages = sum(counts.get(key, 0) for key in
                     ("pages active", "pages wired down", "pages occupied by compressor"))
    free_pages = sum(counts.get(key, 0) for key in
                     ("pages free", "pages inactive", "pages speculative"))
    if not used_pages or not total_b:
        return empty
    total_pages = used_pages + free_pages
    return {
        "percent": round(used_pages * 100 / total_pages),
        "used_gb": round(used_pages * page / 1024 ** 3, 1),
        "total_gb": round(total_b / 1024 ** 3, 1),
    }


def linux_memory_status(meminfo_path: Path = Path("/proc/meminfo")) -> dict:
    """Parse /proc/meminfo for physical memory usage on Linux."""
    empty = {"percent": None, "used_gb": None, "total_gb": None}
    try:
        text = meminfo_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return empty
    values = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * 1024  # kB -> bytes
    total = values.get("MemTotal", 0)
    if total <= 0:
        return empty
    if "MemAvailable" in values:
        avail = values["MemAvailable"]
    else:
        avail = values.get("MemFree", 0) + values.get("Buffers", 0) + values.get("Cached", 0)
    used = max(0, total - avail)
    return {
        "percent": round(used * 100 / total),
        "used_gb": round(used / 1024 ** 3, 1),
        "total_gb": round(total / 1024 ** 3, 1),
    }


def windows_memory_status() -> dict:
    """Query GlobalMemoryStatusEx via ctypes on Windows."""
    empty = {"percent": None, "used_gb": None, "total_gb": None}
    if not hasattr(ctypes, "windll"):
        return empty

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
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        if not ok or stat.ullTotalPhys <= 0:
            return empty
        used = max(0, stat.ullTotalPhys - stat.ullAvailPhys)
        return {
            "percent": int(stat.dwMemoryLoad),
            "used_gb": round(used / 1024 ** 3, 1),
            "total_gb": round(stat.ullTotalPhys / 1024 ** 3, 1),
        }
    except (OSError, AttributeError):
        return empty


def _win_system_times():
    """Read (idle, kernel, user) 100ns ticks via GetSystemTimes."""
    if not hasattr(ctypes, "windll"):
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user),
    )
    if not ok:
        return None
    to_int = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return to_int(idle), to_int(kernel), to_int(user)


def windows_cpu_percent() -> float | None:
    """Compute Windows CPU busy percentage from successive GetSystemTimes calls."""
    global _WIN_PREV_TIMES
    with _WIN_CPU_LOCK:
        prev = _WIN_PREV_TIMES
        now = _win_system_times()
        if now is None:
            return None
        if prev is None:
            time.sleep(0.15)
            prev = now
            now = _win_system_times()
            if now is None:
                return None
        _WIN_PREV_TIMES = now
    d_idle = now[0] - prev[0]
    d_kernel = now[1] - prev[1]
    d_user = now[2] - prev[2]
    total = d_kernel + d_user
    if total <= 0:
        return None
    busy = max(0, total - d_idle)
    return round(min(100.0, busy * 100.0 / total), 1)


def memory_status(system: str | None = None) -> dict:
    """Dispatch physical memory query for the current OS."""
    target = system or platform.system()
    if target == "Darwin":
        return mac_memory_status()
    if target == "Windows":
        return windows_memory_status()
    if target == "Linux":
        return linux_memory_status()
    return {"percent": None, "used_gb": None, "total_gb": None}


def cpu_or_load_status(system: str | None = None) -> dict:
    """Return 1-minute load average on POSIX, or CPU % on Windows."""
    target = system or platform.system()
    if target == "Windows":
        pct = windows_cpu_percent()
        return {
            "kind": "cpu",
            "value": None if pct is None else f"{pct}%",
            "raw": pct,
            "label": "CPU 占用率",
            "hint": "采样周期内的处理器使用百分比。",
        }
    if hasattr(os, "getloadavg"):
        try:
            load = round(os.getloadavg()[0], 2)
            return {
                "kind": "load",
                "value": load,
                "raw": load,
                "label": "系统负载 / 1 分钟",
                "hint": "负载是等待或使用 CPU 的任务数，不是占用百分比。",
            }
        except OSError:
            pass
    return {
        "kind": "load",
        "value": None,
        "raw": None,
        "label": "系统负载",
        "hint": "当前平台不支持读取系统负载。",
    }


def host_snapshot(system: str | None = None) -> dict:
    """Collect cross-platform disk, load/CPU, and memory metrics."""
    target = system or platform.system()
    disk = shutil.disk_usage(Path.home())
    memory = memory_status(target)
    cpu = cpu_or_load_status(target)
    return {
        "platform": target,
        "os_label": {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(target, target),
        "load": cpu["raw"],
        "load_display": cpu["value"],
        "load_kind": cpu["kind"],
        "load_label": cpu["label"],
        "load_hint": cpu["hint"],
        "cores": os.cpu_count(),
        "mem_percent": memory["percent"],
        "mem_used_gb": memory["used_gb"],
        "mem_total_gb": memory["total_gb"],
        "disk_free_gb": round(disk.free / 1024 ** 3, 1),
        "disk_total_gb": round(disk.total / 1024 ** 3, 1),
    }
