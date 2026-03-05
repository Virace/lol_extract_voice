"""配置对象与上下文桥接工具。

该模块用于把当前全局 ``config``（CLI 兼容层）映射为显式对象模型，
为后续 Manager/业务函数改造提供统一的 ``AppContext`` 入口。
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from lol_audio_unpack.utils.config import config
from lol_audio_unpack.utils.type_hints import StrPath


def _to_path(value: Any, key_name: str) -> Path:
    """将输入值转换为 ``Path``。

    Args:
        value: 待转换值。
        key_name: 配置键名，用于异常提示。

    Returns:
        转换后的路径对象。

    Raises:
        ValueError: ``value`` 为空。
    """
    if value is None:
        raise ValueError(f"配置项 {key_name} 不能为空。")
    return Path(value)


def _normalize_types(values: Iterable[Any] | None) -> tuple[str, ...]:
    """标准化音频类型集合。

    Args:
        values: 原始可迭代值。

    Returns:
        仅包含非空大写字符串的不可变元组。
    """
    if not values:
        return ()
    return tuple(str(item).upper() for item in values if str(item).strip())


def _sort_by_known_audio_order(legacy_config: Any, audio_types: tuple[str, ...]) -> tuple[str, ...]:
    """按已知音频类型顺序排序，保证结果稳定。

    Args:
        legacy_config: 兼容层配置对象。
        audio_types: 待排序音频类型。

    Returns:
        排序后的音频类型元组。
    """
    known_order = [
        str(getattr(legacy_config, "AUDIO_TYPE_VO", "VO")).upper(),
        str(getattr(legacy_config, "AUDIO_TYPE_SFX", "SFX")).upper(),
        str(getattr(legacy_config, "AUDIO_TYPE_MUSIC", "MUSIC")).upper(),
    ]
    ordered = [audio_type for audio_type in known_order if audio_type in audio_types]
    extra = sorted(audio_type for audio_type in audio_types if audio_type not in known_order)
    return tuple(ordered + extra)


@dataclass(frozen=True)
class AppConfig:
    """环境级配置快照。"""

    game_path: Path
    output_path: Path
    game_region: str = "zh_CN"
    exclude_types: tuple[str, ...] = ("SFX", "MUSIC")
    include_types: tuple[str, ...] = ("VO",)
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


def build_app_config_from_legacy(legacy_config: Any = config) -> AppConfig:
    """从当前全局配置代理构建 ``AppConfig``。

    Args:
        legacy_config: 兼容层配置对象，默认使用全局 ``config`` 代理。

    Returns:
        可注入的 ``AppConfig`` 实例。
    """
    game_path = _to_path(legacy_config.get("GAME_PATH"), "GAME_PATH")
    output_path = _to_path(legacy_config.get("OUTPUT_PATH"), "OUTPUT_PATH")

    exclude_types = _normalize_types(legacy_config.get("EXCLUDE_TYPE", ()))
    include_types = _normalize_types(legacy_config.get("INCLUDE_TYPE", ()))
    if not include_types:
        known_types = _normalize_types(getattr(legacy_config, "KNOWN_AUDIO_TYPES", ("VO", "SFX", "MUSIC")))
        include_types = tuple(item for item in known_types if item not in exclude_types)
    include_types = _sort_by_known_audio_order(legacy_config, include_types)

    wwiser_path_raw = legacy_config.get("WWISER_PATH")

    return AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=str(legacy_config.get("GAME_REGION", "zh_CN") or "zh_CN"),
        exclude_types=exclude_types,
        include_types=include_types,
        group_by_type=bool(legacy_config.get("GROUP_BY_TYPE", False)),
        with_bp_vo=bool(legacy_config.get("WITH_BP_VO", False)),
        wwiser_path=Path(wwiser_path_raw) if wwiser_path_raw else None,
        dev_mode=bool(legacy_config.is_dev_mode()),
    )


def build_app_paths_from_legacy(legacy_config: Any = config, app_config: AppConfig | None = None) -> AppPaths:
    """从当前全局配置代理构建 ``AppPaths``。

    Args:
        legacy_config: 兼容层配置对象，默认使用全局 ``config`` 代理。
        app_config: 已生成的 ``AppConfig``，传入可避免重复构建。

    Returns:
        可注入的 ``AppPaths`` 实例。
    """
    cfg = app_config or build_app_config_from_legacy(legacy_config)
    output_path = cfg.output_path
    game_path = cfg.game_path

    return AppPaths(
        audio_path=Path(legacy_config.get("AUDIO_PATH", output_path / "audios")),
        temp_path=Path(legacy_config.get("TEMP_PATH", output_path / "temps")),
        log_path=Path(legacy_config.get("LOG_PATH", output_path / "logs")),
        cache_path=Path(legacy_config.get("CACHE_PATH", output_path / "cache")),
        hash_path=Path(legacy_config.get("HASH_PATH", output_path / "hashes")),
        report_path=Path(legacy_config.get("REPORT_PATH", output_path / "reports")),
        manifest_path=Path(legacy_config.get("MANIFEST_PATH", output_path / "manifest")),
        local_version_file=Path(legacy_config.get("LOCAL_VERSION_FILE", output_path / "game_version")),
        game_champion_path=Path(legacy_config.get("GAME_CHAMPION_PATH", game_path / "Game/DATA/FINAL/Champions")),
        game_maps_path=Path(legacy_config.get("GAME_MAPS_PATH", game_path / "Game/DATA/FINAL/Maps/Shipping")),
        game_lcu_path=Path(
            legacy_config.get("GAME_LCU_PATH", game_path / "LeagueClient/Plugins/rcp-be-lol-game-data")
        ),
    )


def build_app_context_from_legacy(
    legacy_config: Any = config,
    runtime_cache: dict[str, Any] | None = None,
) -> AppContext:
    """从全局兼容配置构建 ``AppContext``。

    Args:
        legacy_config: 兼容层配置对象，默认使用全局 ``config`` 代理。
        runtime_cache: 可选运行时缓存字典。

    Returns:
        ``AppContext`` 实例。
    """
    app_config = build_app_config_from_legacy(legacy_config)
    app_paths = build_app_paths_from_legacy(legacy_config, app_config=app_config)
    return AppContext(config=app_config, paths=app_paths, logger=logger, runtime_cache=runtime_cache or {})


def initialize_context_from_env(
    env_path: StrPath | None = None,
    env_prefix: str = "LOL_",
    force_reload: bool = False,
    dev_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
) -> AppContext:
    """初始化全局配置并返回 ``AppContext``。

    Args:
        env_path: 环境变量文件目录路径。
        env_prefix: 环境变量前缀。
        force_reload: 是否强制重载。
        dev_mode: 是否启用开发模式。
        cli_overrides: 命令行覆盖配置。

    Returns:
        初始化后的 ``AppContext``。
    """
    config.initialize(
        env_path=env_path,
        env_prefix=env_prefix,
        force_reload=force_reload,
        dev_mode=dev_mode,
        cli_overrides=cli_overrides,
    )
    return build_app_context_from_legacy(config)


__all__ = [
    "AppConfig",
    "AppContext",
    "AppPaths",
    "OperationOptions",
    "build_app_config_from_legacy",
    "build_app_context_from_legacy",
    "build_app_paths_from_legacy",
    "initialize_context_from_env",
]
