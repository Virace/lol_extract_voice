"""GUI 运行时日志会话管理。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.utils.logging import setup_logging


@dataclass(frozen=True, slots=True)
class RuntimeLoggingSessionState:
    """当前运行时日志会话状态。"""

    log_dir: Path
    log_file: Path
    console_log_level: str
    file_log_level: str


@dataclass(frozen=True, slots=True)
class RuntimeLoggingSessionUpdate:
    """一次运行时日志更新的结果。"""

    log_file: Path
    created_new_file: bool
    reconfigured: bool


class RuntimeLoggingSession:
    """管理 GUI 运行期日志会话文件。"""

    def __init__(
        self,
        *,
        setup_logging_fn: Callable[..., None] = setup_logging,
        now_fn: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._setup_logging = setup_logging_fn
        self._now = now_fn
        self._state: RuntimeLoggingSessionState | None = None

    def apply(
        self,
        payload: RuntimeLoggingConfig,
        *,
        dev_mode: bool = True,
        show_function_info: bool = True,
    ) -> RuntimeLoggingSessionUpdate:
        """应用一次运行时日志配置。"""
        requested_dir = Path(payload.log_dir)
        previous = self._state
        created_new_file = previous is None or requested_dir != previous.log_dir
        log_file = (
            requested_dir / self._now().strftime("%Y-%m-%d_%H-%M-%S.log")
            if created_new_file
            else previous.log_file
        )
        levels_changed = (
            previous is None
            or payload.console_log_level != previous.console_log_level
            or payload.file_log_level != previous.file_log_level
        )
        reconfigured = created_new_file or levels_changed
        if reconfigured:
            self._setup_logging(
                dev_mode=dev_mode,
                log_level=payload.console_log_level,
                file_log_level=payload.file_log_level,
                log_file_path=log_file,
                show_function_info=show_function_info,
            )

        self._state = RuntimeLoggingSessionState(
            log_dir=requested_dir,
            log_file=log_file,
            console_log_level=payload.console_log_level,
            file_log_level=payload.file_log_level,
        )
        return RuntimeLoggingSessionUpdate(
            log_file=log_file,
            created_new_file=created_new_file,
            reconfigured=reconfigured,
        )

    def reset(self) -> None:
        """清空当前会话状态。"""
        self._state = None


_runtime_logging_session = RuntimeLoggingSession()


def apply_runtime_logging_session(
    payload: RuntimeLoggingConfig,
    *,
    dev_mode: bool = True,
    show_function_info: bool = True,
) -> RuntimeLoggingSessionUpdate:
    """应用全局 GUI 运行时日志会话配置。"""
    return _runtime_logging_session.apply(
        payload,
        dev_mode=dev_mode,
        show_function_info=show_function_info,
    )


def reset_runtime_logging_session() -> None:
    """重置全局 GUI 运行时日志会话状态。"""
    _runtime_logging_session.reset()
