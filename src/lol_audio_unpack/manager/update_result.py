"""描述 BIN 更新器内部的逐实体结果。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class UpdateStatus(str, Enum):
    """BIN 实体更新的稳定结果状态。"""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UpdateEntityResult:
    """描述一个英雄或地图的 BIN 更新事实。"""

    entity_type: str
    entity_id: str
    status: UpdateStatus
    entity_name: str = ""
    error_type: str | None = None
    error_message: str | None = None
    artifacts: tuple[str, ...] = ()

    @classmethod
    def success(
        cls,
        entity_type: str,
        entity_id: str,
        *,
        entity_name: str = "",
        artifacts: tuple[str | Path, ...] = (),
    ) -> UpdateEntityResult:
        """构造成功结果。"""
        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            status=UpdateStatus.SUCCESS,
            artifacts=tuple(str(path) for path in artifacts),
        )

    @classmethod
    def incomplete(  # noqa: PLR0913
        cls,
        entity_type: str,
        entity_id: str,
        *,
        entity_name: str = "",
        message: str,
        failed: bool = False,
        artifacts: tuple[str | Path, ...] = (),
    ) -> UpdateEntityResult:
        """构造资源解析不完整的 partial 或 failed 结果。"""
        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            status=UpdateStatus.FAILED if failed else UpdateStatus.PARTIAL,
            error_type="ResourceBindingIncomplete",
            error_message=message,
            artifacts=tuple(str(path) for path in artifacts),
        )

    @classmethod
    def from_error(
        cls,
        entity_type: str,
        entity_id: str,
        error: BaseException,
        *,
        entity_name: str = "",
    ) -> UpdateEntityResult:
        """把逐实体异常转换为稳定失败结果。"""
        return cls(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            status=UpdateStatus.FAILED,
            error_type=type(error).__name__,
            error_message=str(error),
        )


__all__ = ["UpdateEntityResult", "UpdateStatus"]
