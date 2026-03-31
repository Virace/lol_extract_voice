"""运行时日志会话测试。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.gui.controllers.runtime_logging_session import RuntimeLoggingSession

EXPECTED_RECONFIGURE_CALLS = 2


def _payload(
    *,
    log_dir: str = "logs",
    console_level: str = "INFO",
    file_level: str = "DEBUG",
) -> RuntimeLoggingConfig:
    return RuntimeLoggingConfig(
        log_dir=Path(log_dir),
        console_log_level=console_level,
        file_log_level=file_level,
    )


def test_runtime_logging_session_reuses_current_file_when_only_levels_change() -> None:
    calls = []
    session = RuntimeLoggingSession(
        setup_logging_fn=lambda **kwargs: calls.append(kwargs),
        now_fn=lambda: datetime(2026, 3, 31, 8, 17, 5),
    )

    first = session.apply(_payload(console_level="INFO"))
    second = session.apply(_payload(console_level="TRACE"))

    assert first.log_file == Path("logs") / "2026-03-31_08-17-05.log"
    assert second.log_file == first.log_file
    assert first.created_new_file is True
    assert second.created_new_file is False
    assert second.reconfigured is True
    assert calls[0]["log_file_path"] == first.log_file
    assert calls[1]["log_file_path"] == first.log_file


def test_runtime_logging_session_skips_reconfigure_when_payload_unchanged() -> None:
    calls = []
    session = RuntimeLoggingSession(
        setup_logging_fn=lambda **kwargs: calls.append(kwargs),
        now_fn=lambda: datetime(2026, 3, 31, 8, 17, 5),
    )

    first = session.apply(_payload())
    second = session.apply(_payload())

    assert first.reconfigured is True
    assert second.reconfigured is False
    assert len(calls) == 1


def test_runtime_logging_session_creates_new_file_when_directory_changes() -> None:
    calls = []
    timestamps = iter(
        (
            datetime(2026, 3, 31, 8, 17, 5),
            datetime(2026, 3, 31, 8, 18, 20),
        )
    )
    session = RuntimeLoggingSession(
        setup_logging_fn=lambda **kwargs: calls.append(kwargs),
        now_fn=lambda: next(timestamps),
    )

    first = session.apply(_payload(log_dir="logs"))
    second = session.apply(_payload(log_dir="other-logs"))

    assert first.log_file == Path("logs") / "2026-03-31_08-17-05.log"
    assert second.log_file == Path("other-logs") / "2026-03-31_08-18-20.log"
    assert second.created_new_file is True
    assert len(calls) == EXPECTED_RECONFIGURE_CALLS
