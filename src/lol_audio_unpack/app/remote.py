"""应用层 remote 共享类型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RemoteEntityWorkItem:
    """remote 模式下的最小实体工作项。"""

    entity_type: str
    entity_id: int
    need_extract: bool
    need_mapping: bool


@dataclass(frozen=True)
class RemoteEntityCallbackPayload:
    """remote 单位驱动完成后的回调载荷。"""

    entity_type: str
    entity_id: int
    audio_output_paths: tuple[Path, ...] = ()
    mapping_output_path: Path | None = None


__all__ = ["RemoteEntityCallbackPayload", "RemoteEntityWorkItem"]
