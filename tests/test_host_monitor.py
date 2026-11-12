"""Tests for cross-platform host telemetry (macOS, Linux, Windows)."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import host_monitor


class HostMonitorTests(unittest.TestCase):
    VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                1000.
Pages active:                              2000.
Pages inactive:                            1500.
Pages speculative:                          500.
Pages wired down:                           800.
Pages occupied by compressor:               700.
"""

    @patch("host_monitor.subprocess.run")
    def test_mac_memory(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "17179869184\n", ''),
            subprocess.CompletedProcess([], 0, self.VM_STAT, ''),
        ]
        result = host_monitor.mac_memory_status()
        self.assertEqual(result['total_gb'], 16.0)
        self.assertEqual(result['percent'], 54)
        self.assertEqual(result['used_gb'], 0.1)

    @patch("host_monitor.subprocess.run", side_effect=OSError("no sysctl"))
    def test_mac_unavailable(self, run):
        self.assertEqual(host_monitor.mac_memory_status(),
                         {"percent": None, "used_gb": None, "total_gb": None})

    def test_linux_meminfo(self):
        with tempfile.TemporaryDirectory() as tmp:
            meminfo = Path(tmp) / 'meminfo'
            meminfo.write_text(
                "MemTotal:       16384000 kB\n"
                "MemFree:         2048000 kB\n"
                "MemAvailable:    8192000 kB\n",
                encoding='utf-8',
            )
            result = host_monitor.linux_memory_status(meminfo)
        self.assertEqual(result['percent'], 50)
        self.assertGreater(result['total_gb'], 15)

    @patch("host_monitor.windows_cpu_percent", return_value=23.5)
    def test_windows_cpu_label(self, cpu):
        res = host_monitor.cpu_or_load_status("Windows")
        self.assertEqual(res['kind'], 'cpu')
        self.assertEqual(res['value'], '23.5%')
        self.assertIn('CPU', res['label'])

    @patch("host_monitor.memory_status", return_value={"percent": 40, "used_gb": 6.4, "total_gb": 16.0})
    @patch("host_monitor.cpu_or_load_status", return_value={
        "kind": "cpu", "value": "12.0%", "raw": 12.0, "label": "CPU 占用率", "hint": "test",
    })
    def test_host_snapshot_windows(self, cpu, mem):
        snap = host_monitor.host_snapshot("Windows")
        self.assertEqual(snap['os_label'], 'Windows')
        self.assertEqual(snap['load_display'], '12.0%')
        self.assertEqual(snap['mem_percent'], 40)
        self.assertGreater(snap['disk_total_gb'], 0)


if __name__ == '__main__':
    unittest.main()
