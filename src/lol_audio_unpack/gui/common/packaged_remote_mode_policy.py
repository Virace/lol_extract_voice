"""打包版 GUI 远程模式临时限制策略。"""

from __future__ import annotations

from collections.abc import Mapping

from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths

LOCAL_SOURCE_MODE_LABEL = "本地模式"
REMOTE_SOURCE_MODE_LABEL = "远程模式"
LOCAL_SOURCE_MODE_VALUE = "local_path"
REMOTE_SOURCE_MODE_VALUE = "remote_snapshot"

__all__ = [
    "LOCAL_SOURCE_MODE_LABEL",
    "LOCAL_SOURCE_MODE_VALUE",
    "REMOTE_SOURCE_MODE_LABEL",
    "REMOTE_SOURCE_MODE_VALUE",
    "available_source_mode_labels",
    "effective_source_mode",
    "normalize_app_context_settings",
    "packaged_remote_mode_fallback_needed",
    "packaged_remote_mode_disabled",
    "remote_source_panel_visible",
]


def packaged_remote_mode_disabled(*, is_frozen: bool | None = None) -> bool:
    """返回当前 GUI 是否应临时禁用远程模式。

    Args:
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        ``True`` 表示当前为打包态 GUI，应临时禁用远程模式。
    """

    if is_frozen is not None:
        return is_frozen
    return detect_runtime_paths().is_frozen


def effective_source_mode(source_mode: str, *, is_frozen: bool | None = None) -> str:
    """返回当前 GUI 运行时应使用的来源模式。

    Args:
        source_mode: 原始来源模式配置值。
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        打包态下若原值为远程模式，则返回 ``local_path``；否则返回原值。
    """

    normalized_source_mode = str(source_mode or LOCAL_SOURCE_MODE_VALUE)
    if (
        packaged_remote_mode_disabled(is_frozen=is_frozen)
        and normalized_source_mode == REMOTE_SOURCE_MODE_VALUE
    ):
        return LOCAL_SOURCE_MODE_VALUE
    return normalized_source_mode


def available_source_mode_labels(*, is_frozen: bool | None = None) -> list[str]:
    """返回当前 GUI 应展示的来源模式标签列表。

    Args:
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        打包态下仅返回本地模式；源码运行时返回本地与远程模式。
    """

    if packaged_remote_mode_disabled(is_frozen=is_frozen):
        return [LOCAL_SOURCE_MODE_LABEL]
    return [LOCAL_SOURCE_MODE_LABEL, REMOTE_SOURCE_MODE_LABEL]


def packaged_remote_mode_fallback_needed(
    source_mode: str,
    *,
    is_frozen: bool | None = None,
) -> bool:
    """返回当前运行时是否需要提示远程模式已被自动回退。

    Args:
        source_mode: 原始来源模式配置值。
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        仅当当前为打包态，且原始值为远程模式时返回 ``True``。
    """

    return (
        packaged_remote_mode_disabled(is_frozen=is_frozen)
        and str(source_mode or LOCAL_SOURCE_MODE_VALUE) == REMOTE_SOURCE_MODE_VALUE
    )


def remote_source_panel_visible(source_mode: str, *, is_frozen: bool | None = None) -> bool:
    """返回远程配置面板当前是否应显示。

    Args:
        source_mode: 原始来源模式配置值。
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        当运行时有效来源模式仍为远程模式时返回 ``True``。
    """

    return effective_source_mode(source_mode, is_frozen=is_frozen) == REMOTE_SOURCE_MODE_VALUE


def normalize_app_context_settings(
    settings: Mapping[str, str | bool],
    *,
    is_frozen: bool | None = None,
) -> dict[str, str | bool]:
    """归一 GUI 传给 ``create_app_context`` 的共享设置。

    Args:
        settings: GUI 侧准备传递给 ``create_app_context`` 的共享配置映射。
        is_frozen: 可选的冻结态覆写；未提供时按当前运行时自动探测。

    Returns:
        一个浅拷贝后的新字典；如需临时禁用远程模式，会把 ``SOURCE_MODE``
        回退到 ``local_path``。
    """

    normalized = dict(settings)
    normalized[SettingKey.SOURCE_MODE] = effective_source_mode(
        str(normalized.get(SettingKey.SOURCE_MODE, LOCAL_SOURCE_MODE_VALUE) or LOCAL_SOURCE_MODE_VALUE),
        is_frozen=is_frozen,
    )
    return normalized
