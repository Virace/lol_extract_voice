"""GUI 控制器与页面之间共享的合同对象。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeLoggingConfig:
    """运行时日志重配置载荷。"""

    log_dir: Path
    console_log_level: str
    file_log_level: str

    @classmethod
    def from_gui_config(cls, cfg: Any) -> RuntimeLoggingConfig:
        """从当前 GUI 配置构造日志重配置载荷。

        Args:
            cfg: 当前 GUI 配置对象，需提供日志目录与日志等级解析能力。

        Returns:
            RuntimeLoggingConfig: 当前日志系统所需的最小重配置快照。
        """
        return cls(
            log_dir=Path(cfg.resolve_log_dir()),
            console_log_level=str(cfg.console_log_level),
            file_log_level=str(cfg.file_log_level),
        )


@dataclass(frozen=True, slots=True)
class GuiNotice:
    """统一的全局提示请求。"""

    title: str
    content: str
    level: str


@dataclass(frozen=True, slots=True)
class GuiLogMessage:
    """统一的 GUI 日志消息。"""

    level: str
    message: str


@dataclass(frozen=True, slots=True)
class SharedDataLoadingState:
    """共享数据加载状态。"""

    message: str
    active: bool


@dataclass(frozen=True, slots=True)
class EntityRowsPayload:
    """实体列表整体替换或增量更新载荷。"""

    entity_type: str
    rows: tuple[dict[str, Any], ...]

    @classmethod
    def from_rows(
        cls,
        entity_type: str,
        rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    ) -> EntityRowsPayload:
        """从实体行序列构造不可变载荷。

        Args:
            entity_type: 实体类型，如 ``champions`` 或 ``maps``。
            rows: 当前要广播的实体摘要行。

        Returns:
            EntityRowsPayload: 可跨层复用的实体行快照。
        """
        return cls(
            entity_type=entity_type,
            rows=tuple(dict(row) for row in rows),
        )


@dataclass(frozen=True, slots=True)
class QueueProgressUpdate:
    """执行中心进度面板更新载荷。"""

    status_text: str | None = None
    note_text: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None


@dataclass(frozen=True, slots=True)
class OverviewSelectionSyncRequest:
    """从总览页发送到执行中心的选择同步载荷。"""

    source: str
    champion_ids: tuple[int, ...]
    map_ids: tuple[int, ...]
    summary: str
