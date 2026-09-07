"""把本轮执行快照与结构化结果持久化到独立操作目录。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loguru import logger

from .results import RunResult


def _encode_value(value):
    """保留集合结构，路径和枚举转换为稳定的 JSON 值。"""
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"无法记录执行快照中的类型: {type(value).__name__}")


def write_operation_report(  # noqa: PLR0913
    report_root: Path,
    *,
    operation_id: str,
    version: str,
    snapshot: dict[str, Any],
    result: RunResult,
    duration_seconds: float,
    retry_of: str | None = None,
) -> Path | None:
    """记录执行当时的参数与终态，不从后续表单或可覆盖路径反推事实。"""
    report_path = report_root / "operations" / operation_id / "result.json"
    payload = {
        "operation_id": operation_id,
        "version": version,
        "snapshot": snapshot,
        "result": asdict(result),
        "status": result.status.value,
        "duration_seconds": duration_seconds,
        "retry_of": retry_of,
    }
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_encode_value), encoding="utf-8"
        )
    except OSError as exc:
        logger.error("执行报告保存失败，当前结果仍保留在详情中：{}", exc)
        return None
    return report_path
