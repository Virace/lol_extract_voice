"""应用上下文对象与初始化工厂。"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from riotmanifest import LeagueManifestError, LeagueManifestResolver

from lol_audio_unpack.utils.type_hints import StrPath
from lol_audio_unpack.utils.versioning import normalize_patch_version

KNOWN_AUDIO_TYPES: tuple[str, ...] = ("VO", "SFX", "MUSIC")
DEFAULT_REMOTE_LIVE_REGION = "EUW"
SUPPORTED_KEYS: frozenset[str] = frozenset(
    {
        "GAME_PATH",
        "OUTPUT_PATH",
        "GAME_REGION",
        "EXCLUDE_TYPE",
        "CLEANUP_REMOTE",
        "GROUP_BY_TYPE",
        "SOURCE_MODE",
        "REMOTE_LIVE_REGION",
        "REMOTE_VERSION",
        "REMOTE_LCU_MANIFEST_URL",
        "REMOTE_GAME_MANIFEST_URL",
        "WITH_BP_VO",
        "WWISER_PATH",
    }
)
DEFAULT_VALUES: dict[str, Any] = {
    "GAME_REGION": "zh_CN",
    "EXCLUDE_TYPE": "SFX,MUSIC",
    "CLEANUP_REMOTE": True,
    "GROUP_BY_TYPE": False,
    "SOURCE_MODE": "local_path",
    "REMOTE_LIVE_REGION": DEFAULT_REMOTE_LIVE_REGION,
    "WITH_BP_VO": False,
}


class AppContextValidationError(ValueError):
    """应用上下文构建失败异常。"""


class SourceMode(str, Enum):
    """运行时内容来源模式。"""

    LOCAL_PATH = "local_path"
    REMOTE_SNAPSHOT = "remote_snapshot"


@dataclass(frozen=True)
class RemoteSnapshotConfig:
    """远端快照配置。"""

    version: str
    lcu_manifest_url: str
    game_manifest_url: str


@dataclass(frozen=True)
class AppConfig:
    """环境级配置快照。"""

    game_path: Path
    output_path: Path
    game_region: str = "zh_CN"
    exclude_types: tuple[str, ...] = ("SFX", "MUSIC")
    include_types: tuple[str, ...] = ("VO",)
    cleanup_remote: bool = True
    source_mode: SourceMode = SourceMode.LOCAL_PATH
    remote_snapshot: RemoteSnapshotConfig | None = None
    group_by_type: bool = False
    with_bp_vo: bool = False
    wwiser_path: Path | None = None
    dev_mode: bool = False


@dataclass(frozen=True)
class AppPaths:
    """派生路径快照。"""

    audio_path: Path
    temp_path: Path
    log_path: Path
    cache_path: Path
    hash_path: Path
    report_path: Path
    manifest_path: Path
    local_version_file: Path
    game_champion_path: Path
    game_maps_path: Path
    game_lcu_path: Path


@dataclass(frozen=True)
class OperationOptions:
    """一次操作的可变参数。"""

    max_workers: int = 4
    force_update: bool = False
    process_events: bool = True
    integrate_data: bool = False
    champion_ids: tuple[int, ...] | None = None
    map_ids: tuple[int, ...] | None = None


@dataclass
class AppContext:
    """运行时上下文对象。"""

    config: AppConfig
    paths: AppPaths
    logger: Any
    runtime_cache: dict[str, Any] = field(default_factory=dict)


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
    """解析 EXCLUDE_TYPE。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return _normalize_types(part.strip() for part in value.split(","))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return _normalize_types(value)
    return _normalize_types([value])


def _parse_source_mode(value: Any) -> SourceMode:
    """解析内容来源模式。"""
    if isinstance(value, SourceMode):
        return value

    raw_value = str(value or SourceMode.LOCAL_PATH.value).strip().lower()
    try:
        return SourceMode(raw_value)
    except ValueError as exc:
        valid_modes = ", ".join(mode.value for mode in SourceMode)
        raise AppContextValidationError(f"SOURCE_MODE 无效: {raw_value}，可选值: {valid_modes}") from exc


def _normalize_remote_live_region(value: Any) -> str:
    """标准化远端 live 区服。"""
    text = str(value or DEFAULT_REMOTE_LIVE_REGION).strip()
    if not text:
        return DEFAULT_REMOTE_LIVE_REGION
    return text.upper()


def _resolve_latest_remote_snapshot_config(*, live_region: str) -> RemoteSnapshotConfig:
    """自动解析最新 live 快照配置。"""
    try:
        pair = LeagueManifestResolver().resolve_manifest_pair(live_region)
    except LeagueManifestError as exc:
        raise AppContextValidationError(
            f"REMOTE_SNAPSHOT 模式自动解析最新 live 快照失败: live_region={live_region}, error={exc}"
        ) from exc

    version = normalize_patch_version(str(pair.version))
    logger.info(
        "REMOTE_SNAPSHOT 未显式提供快照，已自动解析最新 live 清单：live_region={}, version={}",
        live_region,
        version,
    )
    return RemoteSnapshotConfig(
        version=version,
        lcu_manifest_url=pair.lcu.url,
        game_manifest_url=pair.game.url,
    )


def _to_path(value: Any, key_name: str) -> Path:
    """将输入值转换为 ``Path``。"""
    if value is None:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    text = str(value).strip()
    if not text:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    return Path(text)


def _to_optional_text(value: Any) -> str | None:
    """将输入标准化为可选非空字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_game_path(*, settings: Mapping[str, Any], output_path: Path, source_mode: SourceMode) -> Path:
    """根据来源模式解析游戏根目录。"""
    if source_mode is SourceMode.REMOTE_SNAPSHOT:
        explicit_path = _to_optional_text(settings.get("GAME_PATH"))
        if explicit_path is not None:
            return Path(explicit_path)
        return output_path / "_prepared_game"
    return _to_path(settings.get("GAME_PATH"), "GAME_PATH")


def _build_remote_snapshot_config(
    *,
    settings: Mapping[str, Any],
    source_mode: SourceMode,
) -> RemoteSnapshotConfig | None:
    """根据原始设置构建远端快照配置。"""
    if source_mode is not SourceMode.REMOTE_SNAPSHOT:
        return None

    version = _to_optional_text(settings.get("REMOTE_VERSION"))
    lcu_manifest_url = _to_optional_text(settings.get("REMOTE_LCU_MANIFEST_URL"))
    game_manifest_url = _to_optional_text(settings.get("REMOTE_GAME_MANIFEST_URL"))
    snapshot_fields = {
        "REMOTE_VERSION": version,
        "REMOTE_LCU_MANIFEST_URL": lcu_manifest_url,
        "REMOTE_GAME_MANIFEST_URL": game_manifest_url,
    }
    provided_fields = {key: value for key, value in snapshot_fields.items() if value is not None}

    if provided_fields and len(provided_fields) != len(snapshot_fields):
        missing_fields = [key for key, value in snapshot_fields.items() if value is None]
        missing_text = ", ".join(missing_fields)
        raise AppContextValidationError(
            "REMOTE_SNAPSHOT 模式下若显式指定远端快照，"
            "REMOTE_VERSION、REMOTE_LCU_MANIFEST_URL、REMOTE_GAME_MANIFEST_URL 必须同时提供；"
            f"当前缺少: {missing_text}"
        )

    if provided_fields:
        return RemoteSnapshotConfig(
            version=normalize_patch_version(version),
            lcu_manifest_url=lcu_manifest_url,
            game_manifest_url=game_manifest_url,
        )

    live_region = _normalize_remote_live_region(settings.get("REMOTE_LIVE_REGION"))
    return _resolve_latest_remote_snapshot_config(live_region=live_region)


def _resolve_env_dir(env_path: StrPath | None) -> Path:
    """解析环境文件目录。"""
    if env_path is None:
        return Path.cwd()
    return Path(env_path)


def _select_env_file(env_dir: Path, dev_mode: bool) -> Path:
    """选择实际加载的环境文件。"""
    env_file = env_dir / ".lol.env"
    env_dev_file = env_dir / ".lol.env.dev"
    if dev_mode and env_dev_file.exists():
        return env_dev_file
    return env_file


def _load_prefixed_env_from_file(env_file: Path, env_prefix: str) -> dict[str, str]:
    """从环境文件读取前缀配置。"""
    if not env_file.exists():
        logger.warning(f"环境变量文件不存在: {env_file}")
        return {}

    settings: dict[str, str] = {}
    prefix_len = len(env_prefix)
    min_quoted_length = len("''")
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        normalized_line = stripped_line[7:] if stripped_line.startswith("export ") else stripped_line
        env_name, separator, env_value = normalized_line.partition("=")
        if not separator:
            continue

        env_name = env_name.strip()
        env_value = env_value.strip()
        if (
            len(env_value) >= min_quoted_length
            and env_value[0] == env_value[-1]
            and env_value[0] in {"'", '"'}
        ):
            env_value = env_value[1:-1]
        if not env_name.startswith(env_prefix):
            continue
        key = env_name[prefix_len:]
        if key not in SUPPORTED_KEYS:
            logger.warning(f"忽略未知配置项: {env_name}")
            continue
        settings[key] = env_value
    return settings


def _load_prefixed_env_from_system(env_prefix: str) -> dict[str, str]:
    """从系统环境变量读取前缀配置。"""
    settings: dict[str, str] = {}
    prefix_len = len(env_prefix)
    for env_name, env_value in os.environ.items():
        if not env_name.startswith(env_prefix):
            continue
        key = env_name[prefix_len:]
        if key not in SUPPORTED_KEYS:
            logger.warning(f"忽略未知配置项: {env_name}")
            continue
        settings[key] = env_value
    return settings


def _build_raw_settings(
    *,
    env_path: StrPath | None,
    env_prefix: str,
    dev_mode: bool,
    cli_overrides: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """按优先级合并原始配置。"""
    merged: dict[str, Any] = dict(DEFAULT_VALUES)

    env_dir = _resolve_env_dir(env_path)
    env_file = _select_env_file(env_dir, dev_mode=dev_mode)
    merged.update(_load_prefixed_env_from_file(env_file, env_prefix=env_prefix))
    merged.update(_load_prefixed_env_from_system(env_prefix=env_prefix))

    if cli_overrides:
        for key, value in cli_overrides.items():
            if key not in SUPPORTED_KEYS:
                logger.warning(f"忽略未知CLI配置项: {key}")
                continue
            merged[key] = value

    return merged


def _build_app_config(*, settings: Mapping[str, Any], dev_mode: bool) -> AppConfig:
    """从原始配置构建 ``AppConfig``。"""
    output_path = _to_path(settings.get("OUTPUT_PATH"), "OUTPUT_PATH")
    source_mode = _parse_source_mode(settings.get("SOURCE_MODE"))
    game_path = _resolve_game_path(settings=settings, output_path=output_path, source_mode=source_mode)
    remote_snapshot = _build_remote_snapshot_config(settings=settings, source_mode=source_mode)

    game_region = str(settings.get("GAME_REGION", "zh_CN") or "zh_CN")
    if game_region.lower() == "en_us":
        game_region = "default"

    exclude_types = _parse_exclude_types(settings.get("EXCLUDE_TYPE"))
    include_types = tuple(audio_type for audio_type in KNOWN_AUDIO_TYPES if audio_type not in set(exclude_types))

    wwiser_path_raw = settings.get("WWISER_PATH")

    return AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=game_region,
        exclude_types=exclude_types,
        include_types=include_types,
        cleanup_remote=_parse_bool(settings.get("CLEANUP_REMOTE", True)),
        source_mode=source_mode,
        remote_snapshot=remote_snapshot,
        group_by_type=_parse_bool(settings.get("GROUP_BY_TYPE", False)),
        with_bp_vo=_parse_bool(settings.get("WITH_BP_VO", False)),
        wwiser_path=Path(wwiser_path_raw) if wwiser_path_raw else None,
        dev_mode=dev_mode,
    )


def _build_app_paths(app_config: AppConfig) -> AppPaths:
    """根据 ``AppConfig`` 构建 ``AppPaths``。"""
    output_path = app_config.output_path
    game_path = app_config.game_path

    # 仅派生路径，不在初始化阶段统一创建目录（按需懒创建）。
    audio_path = output_path / "audios"
    temp_path = output_path / "temps"
    log_path = output_path / "logs"
    cache_path = output_path / "cache"
    hash_path = output_path / "hashes"
    report_path = output_path / "reports"
    manifest_path = output_path / "manifest"

    return AppPaths(
        audio_path=audio_path,
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


def create_app_context(  # noqa: PLR0913
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext:
    """构建 ``AppContext``。

    Args:
        env_path: 环境变量文件目录。
        env_prefix: 环境变量前缀。
        force_reload: 兼容参数，当前仅保留签名，不影响行为。
        dev_mode: 是否启用开发模式。
        cli_overrides: CLI 显式覆盖项。
        runtime_cache: 可选运行时缓存。

    Returns:
        构建完成的 ``AppContext``。

    Raises:
        AppContextValidationError: 必填配置缺失时抛出。
    """
    _ = force_reload

    raw_settings = _build_raw_settings(
        env_path=env_path,
        env_prefix=env_prefix,
        dev_mode=dev_mode,
        cli_overrides=cli_overrides,
    )
    app_config = _build_app_config(settings=raw_settings, dev_mode=dev_mode)
    app_paths = _build_app_paths(app_config)
    return AppContext(config=app_config, paths=app_paths, logger=logger, runtime_cache=runtime_cache or {})


def initialize_context_from_env(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
) -> AppContext:
    """兼容入口：从环境构建 ``AppContext``。"""
    return create_app_context(
        env_path=env_path,
        env_prefix=env_prefix,
        force_reload=force_reload,
        dev_mode=dev_mode,
        cli_overrides=cli_overrides,
    )


__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "OperationOptions",
    "RemoteSnapshotConfig",
    "SourceMode",
    "create_app_context",
    "initialize_context_from_env",
]

