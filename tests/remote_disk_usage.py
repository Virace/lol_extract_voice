"""远端集成测试中的目录占用监控工具。"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SIZE_BASE = 1024


def _format_size(num_bytes: int) -> str:
    """把字节数格式化为人类可读字符串。"""
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(num_bytes)
    for unit in units:
        if value < SIZE_BASE or unit == units[-1]:
            return f"{value:.2f}{unit}"
        value /= SIZE_BASE
    return f"{num_bytes}B"


def _compute_unique_disk_usage(root: Path) -> int:
    """统计目录真实占用字节数，按 inode 去重。"""
    if not root.exists():
        return 0

    seen_inodes: set[tuple[int, int]] = set()
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat_result = path.stat()
        inode_key = (stat_result.st_dev, stat_result.st_ino)
        if inode_key in seen_inodes:
            continue
        seen_inodes.add(inode_key)
        total_bytes += stat_result.st_size
    return total_bytes


@dataclass(frozen=True)
class DiskUsageReport:
    """目录占用报告。"""

    label: str
    root: Path
    peak_bytes: int
    final_bytes: int
    duration_seconds: float


class DirectoryUsageMonitor:
    """后台采样目录占用并记录峰值。"""

    def __init__(self, root: Path, *, label: str, interval_seconds: float = 0.5) -> None:
        self.root = root
        self.label = label
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._peak_bytes = 0
        self._start_time = 0.0

    def start(self) -> None:
        """启动后台采样。"""
        self._start_time = time.monotonic()
        self._thread.start()

    def stop(self) -> DiskUsageReport:
        """停止采样并返回最终报告。"""
        self._stop_event.set()
        self._thread.join()
        final_bytes = _compute_unique_disk_usage(self.root)
        self._peak_bytes = max(self._peak_bytes, final_bytes)
        return DiskUsageReport(
            label=self.label,
            root=self.root,
            peak_bytes=self._peak_bytes,
            final_bytes=final_bytes,
            duration_seconds=time.monotonic() - self._start_time,
        )

    def _run(self) -> None:
        """后台采样循环。"""
        while not self._stop_event.is_set():
            self._peak_bytes = max(self._peak_bytes, _compute_unique_disk_usage(self.root))
            self._stop_event.wait(self.interval_seconds)


def write_disk_usage_report(output_path: Path, report: DiskUsageReport) -> Path:
    """把磁盘占用报告追加写入 JSON 文件。"""
    report_path = output_path / "space_usage_reports.json"
    payload = []
    if report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))

    payload.append(
        {
            "label": report.label,
            "root": str(report.root),
            "peak_bytes": report.peak_bytes,
            "peak_human": _format_size(report.peak_bytes),
            "final_bytes": report.final_bytes,
            "final_human": _format_size(report.final_bytes),
            "duration_seconds": round(report.duration_seconds, 3),
        }
    )
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


@contextmanager
def monitor_directory_usage(output_path: Path, *, label: str) -> Iterator[DirectoryUsageMonitor]:
    """在上下文中监控目录占用并输出报告。"""
    monitor = DirectoryUsageMonitor(output_path, label=label)
    monitor.start()
    try:
        yield monitor
    finally:
        report = monitor.stop()
        report_path = write_disk_usage_report(output_path, report)
        print(
            f"[space] {label}: peak={_format_size(report.peak_bytes)}, "
            f"final={_format_size(report.final_bytes)}, "
            f"duration={report.duration_seconds:.2f}s, report={report_path}"
        )
