"""弃用与迁移告警工具。"""

from __future__ import annotations

import warnings
from functools import cache


@cache
def warn_legacy_global_mode(component: str) -> None:
    """发出旧全局模式弃用告警（每组件仅一次）。

    Args:
        component: 调用来源组件名。
    """
    warnings.warn(
        (
            f"[{component}] 当前仍在使用全局 config 回退模式，该模式已弃用；"
            "请迁移到 AppContext + LolAudioUnpackApp（目标移除版本：4.0.0）。"
        ),
        DeprecationWarning,
        stacklevel=3,
    )


__all__ = ["warn_legacy_global_mode"]
