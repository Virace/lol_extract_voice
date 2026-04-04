"""远端快照最小准备器。

说明：
    当前 remote 模式已完成 3 个目标英雄的 `update / extract / mapping`
    真实远端链路验证；后续仍需继续补充地图、更多音频类型与清理策略场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen

from loguru import logger
from riotmanifest import PatcherManifest, WADExtractor

from . import cleanup as remote_cleanup
from . import game as remote_game
from . import lcu as remote_lcu

if TYPE_CHECKING:
    from riotmanifest import PatcherFile

    from lol_audio_unpack.app.context import AppContext
    from lol_audio_unpack.manager import DataReader

LCU_PLUGIN_SUFFIX = "plugins/rcp-be-lol-game-data"
DESCRIPTION_FILE_NAME = "description.json"
CLEANUP_REGISTRY_KEY = "remote_cleanup_registry"
MANIFEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass(frozen=True)
class LcuResult:
    """LCU 最小准备结果。"""

    manifest_cache_path: Path
    description_cache_path: Path
    bundle_cache_paths: tuple[Path, ...]
    prepared_lcu_root: Path


@dataclass(frozen=True)
class BinInputResult:
    """远端 BIN 输入准备结果。"""

    manifest_cache_path: Path
    extracted_file_count: int
    flag_file_path: Path


@dataclass(frozen=True)
class GameWadResult:
    """远端 GAME WAD 准备结果。"""

    manifest_cache_path: Path
    prepared_wad_count: int
    prepared_file_paths: tuple[Path, ...]


__all__ = [
    "RemotePreparer",
    "LcuResult",
    "BinInputResult",
    "GameWadResult",
]


class RemotePreparer:
    """为 `remote_snapshot` 模式准备最小运行环境。"""

    def __init__(self, *, ctx: AppContext) -> None:
        """初始化准备器。

        Args:
            ctx: 运行时上下文。

        Raises:
            ValueError: 当远端快照配置缺失时抛出。
        """
        self.ctx = ctx
        self.snapshot = ctx.config.remote_snapshot
        if self.snapshot is None:
            raise ValueError("REMOTE_SNAPSHOT 模式缺少远端快照配置。")

        self.remote_root = self.ctx.paths.cache_path / "remote" / self.snapshot.version
        self.lcu_cache_root = self.remote_root / "lcu"
        self.game_cache_root = self.remote_root / "game"
        self.lcu_manifest_cache_dir = self.lcu_cache_root / "manifests"
        self.game_manifest_cache_dir = self.game_cache_root / "manifests"
        self.download_root = self.lcu_cache_root / "downloads"
        self.prepared_lcu_root = self.ctx.paths.game_lcu_path

    def cleanup_artifacts(self, *, dry_run: bool = False) -> dict[str, int]:
        """清理本轮已登记的远端准备产物。

        Args:
            dry_run: 为 `True` 时仅统计将删除的数量，不真正删除文件。

        Returns:
            各类产物删除数量统计。
        """
        registry = self._load_cleanup_registry()
        cleanup_counts = {
            "prepared_lcu_wads": self._remove_paths(registry["prepared_lcu_wads"], dry_run=dry_run),
            "cached_lcu_wads": self._remove_paths(registry["cached_lcu_wads"], dry_run=dry_run),
            "bin_input_files": self._remove_paths(registry["bin_input_files"], dry_run=dry_run),
            "bin_input_flags": self._remove_paths(registry["bin_input_flags"], dry_run=dry_run),
            "prepared_game_wads": self._remove_paths(registry["prepared_game_wads"], dry_run=dry_run),
            "cached_game_wads": self._remove_paths(registry["cached_game_wads"], dry_run=dry_run),
        }

        if not dry_run:
            self._prune_empty_tree(self.ctx.paths.manifest_path / self.snapshot.version / "bin_input")
            self._prune_empty_tree(self.prepared_lcu_root)
            self._prune_empty_tree(self.game_cache_root / "downloads")
            self._prune_empty_tree(self.lcu_cache_root / "downloads")
            self._prune_empty_tree(self.ctx.config.game_path / "Game" / "DATA" / "FINAL" / "Champions")
            self._prune_empty_tree(self.ctx.config.game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping")
            self.ctx.runtime_cache.pop(CLEANUP_REGISTRY_KEY, None)

        return cleanup_counts

    def prepare_lcu_data(self) -> LcuResult:
        """准备 `DataUpdater` 所需的 LCU 基础资源。

        Returns:
            本次准备产生的缓存与落盘信息。
        """
        manifest_cache_path = self._ensure_manifest_cached(
            manifest_url=self.snapshot.lcu_manifest_url,
            manifest_cache_dir=self.lcu_manifest_cache_dir,
        )
        manifest = PatcherManifest(file=manifest_cache_path, path=self.download_root)

        lcu_files = remote_lcu.collect_files(manifest, get_relative_path=self._get_lcu_path)
        description_file = remote_lcu.find_description(lcu_files, description_file_name=DESCRIPTION_FILE_NAME)
        description_cache_path = self._ensure_files_downloaded(manifest, [description_file])[0]
        self._sync_lcu_file(description_cache_path)

        bundle_names = remote_lcu.resolve_bundle_names(
            description_cache_path,
            region=self.ctx.config.game_region,
        )
        bundle_files = remote_lcu.resolve_bundle_files(bundle_names, lcu_files)
        bundle_cache_paths = tuple(self._ensure_files_downloaded(manifest, bundle_files))
        prepared_bundle_paths: list[Path] = []
        for bundle_cache_path in bundle_cache_paths:
            prepared_bundle_paths.append(self._sync_lcu_file(bundle_cache_path))

        self._track_cleanup_paths("cached_lcu_wads", bundle_cache_paths)
        self._track_cleanup_paths("prepared_lcu_wads", prepared_bundle_paths)

        logger.info(
            "远端 LCU 最小准备完成：version={}, region={}, bundles={}",
            self.snapshot.version,
            self.ctx.config.game_region,
            len(bundle_cache_paths),
        )
        return LcuResult(
            manifest_cache_path=manifest_cache_path,
            description_cache_path=description_cache_path,
            bundle_cache_paths=bundle_cache_paths,
            prepared_lcu_root=self.prepared_lcu_root,
        )

    def prepare_bin_inputs(
        self,
        *,
        reader: DataReader,
        target: str,
        champion_ids: tuple[int, ...] | None = None,
        map_ids: tuple[int, ...] | None = None,
    ) -> BinInputResult | None:
        """从远端 GAME manifest 提取 `BinUpdater` 所需的 BIN 输入。

        Args:
            reader: 已初始化的数据读取器。
            target: 当前更新目标，取值与 `BinUpdater.update()` 一致。
            champion_ids: 指定英雄 ID 集合。
            map_ids: 指定地图 ID 集合。

        Returns:
            提取结果；若没有任何目标 BIN，返回 `None`。
        """
        extraction_plan = remote_game.build_bin_plan(
            reader=reader,
            target=target,
            champion_ids=champion_ids,
            map_ids=map_ids,
        )
        if not extraction_plan:
            logger.warning("远端 GAME 快照未规划到任何 BIN 提取目标，已跳过 BIN 输入准备。")
            return None

        planned_wad_count = len(extraction_plan)
        planned_bin_count = sum(len(bin_paths) for bin_paths in extraction_plan.values())
        logger.info(
            "开始准备远端 BIN 输入：target={}，WAD {} 个，BIN {} 个",
            target,
            planned_wad_count,
            planned_bin_count,
        )

        manifest_cache_path = self._ensure_manifest_cached(
            manifest_url=self.snapshot.game_manifest_url,
            manifest_cache_dir=self.game_manifest_cache_dir,
        )
        manifest = PatcherManifest(file=manifest_cache_path, path=self.game_cache_root / "downloads")
        extractor = WADExtractor(manifest)

        bin_input_root = self.ctx.paths.manifest_path / self.snapshot.version / "bin_input"
        extracted_count = 0
        extracted_paths: list[Path] = []
        for wad_path, bin_paths in extraction_plan.items():
            extraction_result = extractor.extract_files({wad_path: bin_paths})
            wad_results = extraction_result.get(wad_path, {})
            for bin_path, payload in wad_results.items():
                if payload is None:
                    logger.warning(f"远端 BIN 提取失败或缺失: wad={wad_path}, bin={bin_path}")
                    continue
                target_path = bin_input_root / bin_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(payload)
                extracted_paths.append(target_path)
                extracted_count += 1

        flag_file_path = self.ctx.paths.manifest_path / self.snapshot.version / ".use_local_bin"
        if extracted_count > 0:
            flag_file_path.parent.mkdir(parents=True, exist_ok=True)
            flag_file_path.touch()
            self._track_cleanup_paths("bin_input_files", extracted_paths)
            self._track_cleanup_paths("bin_input_flags", [flag_file_path])
            logger.info("远端 BIN 输入准备完成：共提取 {} 个文件。", extracted_count)
            return BinInputResult(
                manifest_cache_path=manifest_cache_path,
                extracted_file_count=extracted_count,
                flag_file_path=flag_file_path,
            )

        logger.warning("远端 BIN 输入准备未成功写入任何文件。")
        return None

    def prepare_extract_wads(
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
    ) -> GameWadResult | None:
        """准备远端 `extract` 阶段所需的实体 WAD。"""
        wad_paths = remote_game.build_extract_plan(
            reader=reader,
            champion_ids=champion_ids,
            map_ids=map_ids,
            include_champions=include_champions,
            include_maps=include_maps,
        )
        return self._prepare_wads(wad_paths)

    def prepare_mapping_wads(
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
    ) -> GameWadResult | None:
        """准备远端 `mapping` 阶段所需的实体 WAD。"""
        wad_paths = remote_game.build_mapping_plan(
            reader=reader,
            champion_ids=champion_ids,
            map_ids=map_ids,
            include_champions=include_champions,
            include_maps=include_maps,
        )
        return self._prepare_wads(wad_paths)

    def prepare_entity_wads(  # noqa: PLR0913
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
        need_extract: bool,
        need_mapping: bool,
    ) -> GameWadResult | None:
        """为单个实体工作项准备所需 WAD 并集。"""
        wad_paths: set[str] = set()
        if need_extract:
            wad_paths.update(
                remote_game.build_extract_plan(
                    reader=reader,
                    champion_ids=champion_ids,
                    map_ids=map_ids,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )
            )
        if need_mapping:
            wad_paths.update(
                remote_game.build_mapping_plan(
                    reader=reader,
                    champion_ids=champion_ids,
                    map_ids=map_ids,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )
            )
        if wad_paths:
            logger.info(
                "开始准备远端 GAME WAD：extract={}，mapping={}，目标 {} 个",
                "开启" if need_extract else "关闭",
                "开启" if need_mapping else "关闭",
                len(wad_paths),
            )
        return self._prepare_wads(wad_paths)

    def _ensure_manifest_cached(self, *, manifest_url: str, manifest_cache_dir: Path) -> Path:
        """缓存远端 manifest 文件。"""
        return remote_lcu.ensure_manifest_cached(
            manifest_url=manifest_url,
            manifest_cache_dir=manifest_cache_dir,
            headers=MANIFEST_HEADERS,
            request_open=urlopen,
        )

    def _ensure_files_downloaded(
        self,
        manifest: PatcherManifest,
        files: list[PatcherFile],
    ) -> list[Path]:
        """确保目标文件已下载到缓存目录。"""
        return remote_lcu.ensure_files_downloaded(
            manifest,
            files,
            run_coroutine_sync=self._run_sync,
        )

    def _prepare_wads(self, wad_paths: set[str]) -> GameWadResult | None:
        """下载并同步远端 GAME WAD 到最小运行目录。"""
        return remote_game.prepare_wads(
            preparer=self,
            wad_paths=wad_paths,
            manifest_class=PatcherManifest,
            result_class=GameWadResult,
        )

    def _sync_lcu_file(self, source_path: Path) -> Path:
        """把 LCU 缓存文件同步到最小运行目录。"""
        relative_path = self._get_lcu_path(source_path.relative_to(self.download_root).as_posix())
        if relative_path is None:
            raise ValueError(f"无法识别 LCU 相对路径: {source_path}")

        target_path = self.prepared_lcu_root / relative_path
        self._link_or_copy(source_path, target_path)
        return target_path

    def _sync_game_file(self, source_path: Path, download_root: Path) -> Path:
        """把 GAME 缓存文件同步到最小运行目录。"""
        relative_path = source_path.relative_to(download_root)
        target_path = self.ctx.config.game_path / "Game" / relative_path
        self._link_or_copy(source_path, target_path)
        return target_path

    @staticmethod
    def _run_sync(coroutine: Any) -> Any:
        """在同步上下文中执行协程。"""
        return remote_cleanup.run_sync(coroutine)

    @staticmethod
    def _get_lcu_path(file_name: str) -> PurePosixPath | None:
        """提取相对于 `rcp-be-lol-game-data` 根目录的路径。"""
        return remote_cleanup.get_lcu_path(file_name, plugin_suffix=LCU_PLUGIN_SUFFIX)

    @staticmethod
    def _link_or_copy(source_path: Path, target_path: Path) -> None:
        """优先硬链接，失败时回退复制。"""
        remote_cleanup.link_or_copy(source_path, target_path)

    def _load_cleanup_registry(self) -> dict[str, set[str]]:
        """获取或初始化远端清理登记表。"""
        return remote_cleanup.load_registry(
            self.ctx.runtime_cache,
            cache_key=CLEANUP_REGISTRY_KEY,
        )

    def _track_cleanup_paths(self, key: str, paths: list[Path] | tuple[Path, ...]) -> None:
        """登记可清理文件路径。"""
        remote_cleanup.track_paths(self._load_cleanup_registry(), key, paths)

    @staticmethod
    def _remove_paths(paths: set[str], *, dry_run: bool) -> int:
        """删除或统计已登记路径数量。"""
        return remote_cleanup.remove_paths(paths, dry_run=dry_run)

    @staticmethod
    def _prune_empty_tree(root: Path) -> None:
        """删除根目录下的空目录。"""
        remote_cleanup.prune_empty_tree(root)

