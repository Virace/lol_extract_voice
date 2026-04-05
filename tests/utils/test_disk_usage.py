import os
from pathlib import Path

import pytest

from lol_audio_unpack.utils.disk_usage import (
    DiskUsageReport,
    compute_unique_disk_usage,
    format_size,
    write_disk_usage_report,
)

pytestmark = pytest.mark.unit
FILE_SIZE_BYTES = 16


def test_compute_unique_disk_usage_deduplicates_hardlinks(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"a" * FILE_SIZE_BYTES)
    linked = tmp_path / "linked.bin"
    os.link(source, linked)

    assert compute_unique_disk_usage(tmp_path) == FILE_SIZE_BYTES


def test_compute_unique_disk_usage_ignores_racing_deleted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class DisappearingPath:
        def is_file(self) -> bool:
            return True

        def stat(self):
            raise FileNotFoundError

    monkeypatch.setattr(Path, "rglob", lambda self, pattern: [DisappearingPath()])

    assert compute_unique_disk_usage(tmp_path) == 0


def test_format_size_returns_human_readable_text() -> None:
    assert format_size(1024) == "1.00KiB"


def test_write_disk_usage_report_appends_records(tmp_path: Path) -> None:
    first = DiskUsageReport(label="a", root=tmp_path, peak_bytes=10, final_bytes=5, duration_seconds=1.2)
    second = DiskUsageReport(label="b", root=tmp_path, peak_bytes=20, final_bytes=6, duration_seconds=2.3)

    report_path = write_disk_usage_report(tmp_path, first)
    write_disk_usage_report(tmp_path, second)

    content = report_path.read_text(encoding="utf-8")
    assert '"label": "a"' in content
    assert '"label": "b"' in content
