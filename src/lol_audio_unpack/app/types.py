"""应用层共享类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


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
    """独立 WAV 转码 stage 的输出配置。"""

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


__all__ = [
    "AppConfig",
    "AppContext",
    "AppContextValidationError",
    "AppPaths",
    "OperationOptions",
    "RemoteSnapshotConfig",
    "SourceMode",
    "WavOutputOptions",
]
