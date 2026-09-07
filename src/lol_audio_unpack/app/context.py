"""应用上下文对象与初始化工厂。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from loguru import logger

from lol_audio_unpack.config import (
    DEFAULT_SHARED_SETTINGS,
    SUPPORTED_SETTING_KEYS,
    SettingKey,
)
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_root,
    resolve_runtime_path,
)

from .local_source import validate_local_source
from .types import (
    AppConfig,
    AppContext,
    AppContextValidationError,
    AppPaths,
    OperationOptions,
    WavOutputOptions,
)

KNOWN_AUDIO_TYPES: tuple[str, ...] = ("VO", "SFX", "MUSIC")


def _parse_bool(value: Any) -> bool:
    """解析布尔配置值。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "t"}
    return bool(value)


def _normalize_types(values: Iterable[Any] | None) -> tuple[str, ...]:
    """标准化音频类型集合。"""
    if values is None:
        return ()
    return tuple(str(item).upper() for item in values if str(item).strip())


def _parse_exclude_types(value: Any) -> tuple[str, ...]:
    """解析排除音频类型设置。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return _normalize_types(part.strip() for part in value.split(","))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return _normalize_types(value)
    return _normalize_types([value])


def _to_runtime_path(value: Any, key_name: str, *, runtime_root: Path) -> Path:
    """按统一 runtime 语义将输入转换为绝对 ``Path``。"""
    if value is None:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    text = str(value).strip()
    if not text:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    return resolve_runtime_path(text, relative_to=runtime_root)


def _build_settings(
    *,
    settings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """按默认值和显式输入合并原始配置。"""
    merged: dict[str, Any] = dict(DEFAULT_SHARED_SETTINGS)
    merged[SettingKey.OUTPUT_PATH] = get_default_output_root(detect_runtime_paths())

    if settings:
        for key, value in settings.items():
            if key not in SUPPORTED_SETTING_KEYS:
                logger.warning(f"忽略未知配置项: {key}")
                continue
            if value is None:
                logger.debug(f"忽略空的配置项: {key}=None")
                continue
            if isinstance(value, str) and not value.strip():
                if key == SettingKey.EXCLUDE_TYPE:
                    merged[key] = ""
                    continue
                logger.debug(f"忽略空白配置项: {key}")
                continue
            merged[key] = value

    return merged


def _build_config(*, settings: Mapping[str, Any], dev_mode: bool) -> AppConfig:
    """从原始配置构建 ``AppConfig``。"""
    runtime_root = detect_runtime_paths().launch_root
    output_path = _to_runtime_path(
        settings.get(SettingKey.OUTPUT_PATH),
        SettingKey.OUTPUT_PATH,
        runtime_root=runtime_root,
    )
    game_path = _to_runtime_path(
        settings.get(SettingKey.GAME_PATH),
        SettingKey.GAME_PATH,
        runtime_root=runtime_root,
    )

    game_region = str(settings.get(SettingKey.GAME_REGION, "zh_CN") or "zh_CN")
    if game_region.lower() == "en_us":
        game_region = "default"

    exclude_types = _parse_exclude_types(settings.get(SettingKey.EXCLUDE_TYPE))
    include_types = tuple(audio_type for audio_type in KNOWN_AUDIO_TYPES if audio_type not in set(exclude_types))

    wwiser_path_raw = settings.get(SettingKey.WWISER_PATH)

    return AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=game_region,
        exclude_types=exclude_types,
        include_types=include_types,
        group_by_type=_parse_bool(settings.get(SettingKey.GROUP_BY_TYPE, False)),
        with_bp_vo=_parse_bool(settings.get(SettingKey.WITH_BP_VO, False)),
        wwiser_path=(
            resolve_runtime_path(str(wwiser_path_raw).strip(), relative_to=runtime_root) if wwiser_path_raw else None
        ),
        dev_mode=dev_mode,
    )


def _build_paths(app_config: AppConfig) -> AppPaths:
    """根据 ``AppConfig`` 构建 ``AppPaths``。"""
    output_path = app_config.output_path
    game_path = app_config.game_path

    # 仅派生路径，不在初始化阶段统一创建目录（按需懒创建）。
    audio_path = output_path / "audios"
    wav_path = output_path / "wavs"
    temp_path = output_path / "temps"
    log_path = output_path / "logs"
    cache_path = output_path / "cache"
    hash_path = output_path / "hashes"
    report_path = output_path / "reports"
    manifest_path = output_path / "manifest"

    return AppPaths(
        audio_path=audio_path,
        wav_path=wav_path,
        temp_path=temp_path,
        log_path=log_path,
        cache_path=cache_path,
        hash_path=hash_path,
        report_path=report_path,
        manifest_path=manifest_path,
        local_version_file=output_path / "game_version",
        game_champion_path=game_path / "Game" / "DATA" / "FINAL" / "Champions",
        game_maps_path=game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
        game_lcu_path=game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
    )


def create_app_context(
    *,
    settings: Mapping[str, Any] | None = None,
    force_reload: bool = False,
    dev_mode: bool = False,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext:
    """构建 ``AppContext``。

    Args:
        settings: 已解析完成的共享配置输入。
        force_reload: 兼容参数，当前仅保留签名，不影响行为。
        dev_mode: 是否启用开发模式。
        runtime_cache: 可选运行时缓存。

    Returns:
        构建完成的 ``AppContext``。

    Raises:
        AppContextValidationError: 必填配置缺失时抛出。
    """
    _ = force_reload

    raw_settings = _build_settings(settings=settings)
    app_config = _build_config(settings=raw_settings, dev_mode=dev_mode)
    validate_local_source(app_config.game_path)
    app_paths = _build_paths(app_config)
    return AppContext(config=app_config, paths=app_paths, runtime_cache=runtime_cache or {})


__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "OperationOptions",
    "WavOutputOptions",
    "create_app_context",
]
