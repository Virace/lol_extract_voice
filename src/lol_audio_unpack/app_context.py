"""应用上下文对象与初始化工厂。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger
from riotmanifest import LeagueManifestError, LeagueManifestResolver

from lol_audio_unpack.config_schema import (
    DEFAULT_REMOTE_LIVE_REGION,
    DEFAULT_SHARED_SETTINGS,
    SUPPORTED_SETTING_KEYS,
    SettingKey,
)
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_output_root,
    resolve_runtime_path,
)
from lol_audio_unpack.utils.type_hints import StrPath
from lol_audio_unpack.utils.versioning import normalize_patch_version

KNOWN_AUDIO_TYPES: tuple[str, ...] = ("VO", "SFX", "MUSIC")


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
class WavOutputOptions:
    """WAV sidecar 派生输出配置。"""

    enabled: bool = False
    worker_count: int = 2
    timeout_seconds: int = 5
    max_retries: int = 3
    format: str = "pcm16"


@dataclass(frozen=True)
class AppPaths:
    """派生路径快照。"""

    audio_path: Path
    wav_path: Path
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
    wav_output: WavOutputOptions = field(default_factory=WavOutputOptions)


@dataclass
class AppContext:
    """运行时上下文对象。"""

    config: AppConfig
    paths: AppPaths
    runtime_cache: dict[str, Any] = field(default_factory=dict)

    @property
    def game_path(self) -> Path:
        """返回标准化后的游戏根目录。

        Returns:
            Path: 游戏根目录。
        """
        return self.config.game_path

    @property
    def game_region(self) -> str:
        """返回标准化后的语言区域。

        Returns:
            str: 当前语言区域。
        """
        return self.config.game_region

    @property
    def wwiser_path(self) -> Path | None:
        """返回标准化后的 wwiser 路径。

        Returns:
            Path | None: 配置中的 wwiser 文件路径；未配置时返回 ``None``。
        """
        return self.config.wwiser_path

    @property
    def include_types(self) -> tuple[str, ...]:
        """返回包含的音频类型集合。

        Returns:
            tuple[str, ...]: 当前启用的音频类型。
        """
        return self.config.include_types

    @property
    def exclude_types(self) -> tuple[str, ...]:
        """返回排除的音频类型集合。

        Returns:
            tuple[str, ...]: 当前排除的音频类型。
        """
        return self.config.exclude_types

    @property
    def group_by_type(self) -> bool:
        """返回是否按音频类型优先分组输出。

        Returns:
            bool: ``True`` 表示按类型分组。
        """
        return self.config.group_by_type

    @property
    def audio_path(self) -> Path:
        """返回音频输出根目录。

        Returns:
            Path: 音频输出根目录。
        """
        return self.paths.audio_path

    @property
    def wav_path(self) -> Path:
        """返回 WAV 输出根目录。

        Returns:
            Path: WAV 输出根目录。
        """
        return self.paths.wav_path

    @property
    def cache_path(self) -> Path:
        """返回 cache 根目录。

        Returns:
            Path: cache 根目录。
        """
        return self.paths.cache_path

    @property
    def hash_path(self) -> Path:
        """返回 hashes 根目录。

        Returns:
            Path: hashes 根目录。
        """
        return self.paths.hash_path

    @property
    def report_path(self) -> Path:
        """返回报告输出根目录。

        Returns:
            Path: 报告输出根目录。
        """
        return self.paths.report_path


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


def _parse_source_mode(value: Any) -> SourceMode:
    """解析内容来源模式。"""
    if isinstance(value, SourceMode):
        return value

    raw_value = str(value or SourceMode.LOCAL_PATH.value).strip().lower()
    try:
        return SourceMode(raw_value)
    except ValueError as exc:
        valid_modes = ", ".join(mode.value for mode in SourceMode)
        raise AppContextValidationError(f"{SettingKey.SOURCE_MODE} 无效: {raw_value}，可选值: {valid_modes}") from exc


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


def _to_runtime_path(value: Any, key_name: str, *, runtime_root: Path) -> Path:
    """按统一 runtime 语义将输入转换为绝对 ``Path``。"""
    if value is None:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    text = str(value).strip()
    if not text:
        raise AppContextValidationError(f"缺少必要的配置项: {key_name}")
    return resolve_runtime_path(text, relative_to=runtime_root)


def _to_optional_text(value: Any) -> str | None:
    """将输入标准化为可选非空字符串。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_game_path(
    *,
    settings: Mapping[str, Any],
    output_path: Path,
    source_mode: SourceMode,
    runtime_root: Path,
) -> Path:
    """根据来源模式解析游戏根目录。"""
    if source_mode is SourceMode.REMOTE_SNAPSHOT:
        explicit_path = _to_optional_text(settings.get(SettingKey.GAME_PATH))
        if explicit_path is not None:
            return resolve_runtime_path(explicit_path, relative_to=runtime_root)
        return output_path / "_prepared_game"
    return _to_runtime_path(settings.get(SettingKey.GAME_PATH), SettingKey.GAME_PATH, runtime_root=runtime_root)


def _build_remote_snapshot_config(
    *,
    settings: Mapping[str, Any],
    source_mode: SourceMode,
) -> RemoteSnapshotConfig | None:
    """根据原始设置构建远端快照配置。"""
    if source_mode is not SourceMode.REMOTE_SNAPSHOT:
        return None

    version = _to_optional_text(settings.get(SettingKey.REMOTE_VERSION))
    lcu_manifest_url = _to_optional_text(settings.get(SettingKey.REMOTE_LCU_MANIFEST_URL))
    game_manifest_url = _to_optional_text(settings.get(SettingKey.REMOTE_GAME_MANIFEST_URL))
    snapshot_fields = {
        SettingKey.REMOTE_VERSION: version,
        SettingKey.REMOTE_LCU_MANIFEST_URL: lcu_manifest_url,
        SettingKey.REMOTE_GAME_MANIFEST_URL: game_manifest_url,
    }
    provided_fields = {key: value for key, value in snapshot_fields.items() if value is not None}

    if provided_fields and len(provided_fields) != len(snapshot_fields):
        missing_fields = [key for key, value in snapshot_fields.items() if value is None]
        missing_text = ", ".join(missing_fields)
        raise AppContextValidationError(
            "REMOTE_SNAPSHOT 模式下若显式指定远端快照，"
            f"{SettingKey.REMOTE_VERSION}、{SettingKey.REMOTE_LCU_MANIFEST_URL}、"
            f"{SettingKey.REMOTE_GAME_MANIFEST_URL} 必须同时提供；"
            f"当前缺少: {missing_text}"
        )

    if provided_fields:
        return RemoteSnapshotConfig(
            version=normalize_patch_version(version),
            lcu_manifest_url=lcu_manifest_url,
            game_manifest_url=game_manifest_url,
        )

    live_region = _normalize_remote_live_region(settings.get(SettingKey.REMOTE_LIVE_REGION))
    return _resolve_latest_remote_snapshot_config(live_region=live_region)


def _build_raw_settings(
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


def _build_app_config(*, settings: Mapping[str, Any], dev_mode: bool) -> AppConfig:
    """从原始配置构建 ``AppConfig``。"""
    runtime_root = detect_runtime_paths().launch_root
    output_path = _to_runtime_path(
        settings.get(SettingKey.OUTPUT_PATH),
        SettingKey.OUTPUT_PATH,
        runtime_root=runtime_root,
    )
    source_mode = _parse_source_mode(settings.get(SettingKey.SOURCE_MODE))
    game_path = _resolve_game_path(
        settings=settings,
        output_path=output_path,
        source_mode=source_mode,
        runtime_root=runtime_root,
    )
    remote_snapshot = _build_remote_snapshot_config(settings=settings, source_mode=source_mode)

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
        cleanup_remote=_parse_bool(settings.get(SettingKey.CLEANUP_REMOTE, True)),
        source_mode=source_mode,
        remote_snapshot=remote_snapshot,
        group_by_type=_parse_bool(settings.get(SettingKey.GROUP_BY_TYPE, False)),
        with_bp_vo=_parse_bool(settings.get(SettingKey.WITH_BP_VO, False)),
        wwiser_path=(
            resolve_runtime_path(str(wwiser_path_raw).strip(), relative_to=runtime_root)
            if wwiser_path_raw
            else None
        ),
        dev_mode=dev_mode,
    )


def _build_app_paths(app_config: AppConfig) -> AppPaths:
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

    raw_settings = _build_raw_settings(settings=settings)
    app_config = _build_app_config(settings=raw_settings, dev_mode=dev_mode)
    app_paths = _build_app_paths(app_config)
    return AppContext(config=app_config, paths=app_paths, runtime_cache=runtime_cache or {})


__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "OperationOptions",
    "RemoteSnapshotConfig",
    "SourceMode",
    "WavOutputOptions",
    "create_app_context",
]
