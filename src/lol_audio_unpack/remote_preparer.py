"""远端快照最小准备器。

说明：
    当前 remote 模式已完成 3 个目标英雄的 `update / extract / mapping`
    真实远端链路验证；后续仍需继续补充地图、更多音频类型与清理策略场景。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen

from loguru import logger
from riotmanifest import PatcherManifest, WADExtractor

if TYPE_CHECKING:
    from riotmanifest import PatcherFile

    from lol_audio_unpack.app_context import AppContext
    from lol_audio_unpack.manager import DataReader

LCU_PLUGIN_SUFFIX = "plugins/rcp-be-lol-game-data"
DESCRIPTION_FILE_NAME = "description.json"
REMOTE_CLEANUP_REGISTRY_KEY = "remote_cleanup_registry"
REMOTE_MANIFEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


@dataclass(frozen=True)
class LcuPrepareResult:
    """LCU 最小准备结果。"""

    manifest_cache_path: Path
    description_cache_path: Path
    bundle_cache_paths: tuple[Path, ...]
    prepared_lcu_root: Path


@dataclass(frozen=True)
class BinInputPrepareResult:
    """远端 BIN 输入准备结果。"""

    manifest_cache_path: Path
    extracted_file_count: int
    flag_file_path: Path


@dataclass(frozen=True)
class GameWadPrepareResult:
    """远端 GAME WAD 准备结果。"""

    manifest_cache_path: Path
    prepared_wad_count: int
    prepared_file_paths: tuple[Path, ...]


class RemoteSnapshotPreparer:
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

    def cleanup_tracked_artifacts(self, *, dry_run: bool = False) -> dict[str, int]:
        """清理本轮已登记的远端准备产物。

        Args:
            dry_run: 为 `True` 时仅统计将删除的数量，不真正删除文件。

        Returns:
            各类产物删除数量统计。
        """
        registry = self._get_cleanup_registry()
        cleanup_counts = {
            "prepared_lcu_wads": self._remove_registered_paths(registry["prepared_lcu_wads"], dry_run=dry_run),
            "cached_lcu_wads": self._remove_registered_paths(registry["cached_lcu_wads"], dry_run=dry_run),
            "bin_input_files": self._remove_registered_paths(registry["bin_input_files"], dry_run=dry_run),
            "bin_input_flags": self._remove_registered_paths(registry["bin_input_flags"], dry_run=dry_run),
            "prepared_game_wads": self._remove_registered_paths(registry["prepared_game_wads"], dry_run=dry_run),
            "cached_game_wads": self._remove_registered_paths(registry["cached_game_wads"], dry_run=dry_run),
        }

        if not dry_run:
            self._prune_empty_tree(self.ctx.paths.manifest_path / self.snapshot.version / "bin_input")
            self._prune_empty_tree(self.prepared_lcu_root)
            self._prune_empty_tree(self.game_cache_root / "downloads")
            self._prune_empty_tree(self.lcu_cache_root / "downloads")
            self._prune_empty_tree(self.ctx.config.game_path / "Game" / "DATA" / "FINAL" / "Champions")
            self._prune_empty_tree(self.ctx.config.game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping")
            self.ctx.runtime_cache.pop(REMOTE_CLEANUP_REGISTRY_KEY, None)

        return cleanup_counts

    def prepare_lcu_game_data(self) -> LcuPrepareResult:
        """准备 `DataUpdater` 所需的 LCU 基础资源。

        Returns:
            本次准备产生的缓存与落盘信息。
        """
        manifest_cache_path = self._ensure_manifest_cached(
            manifest_url=self.snapshot.lcu_manifest_url,
            manifest_cache_dir=self.lcu_manifest_cache_dir,
        )
        manifest = PatcherManifest(file=manifest_cache_path, path=self.download_root)

        lcu_files = self._collect_lcu_files(manifest)
        description_file = self._find_description_file(lcu_files)
        description_cache_path = self._ensure_manifest_files_downloaded(manifest, [description_file])[0]
        self._sync_lcu_file_to_prepared_root(description_cache_path)

        bundle_names = self._resolve_required_bundle_names(description_cache_path)
        bundle_files = self._resolve_bundle_files(bundle_names, lcu_files)
        bundle_cache_paths = tuple(self._ensure_manifest_files_downloaded(manifest, bundle_files))
        prepared_bundle_paths: list[Path] = []
        for bundle_cache_path in bundle_cache_paths:
            prepared_bundle_paths.append(self._sync_lcu_file_to_prepared_root(bundle_cache_path))

        self._register_cleanup_paths("cached_lcu_wads", bundle_cache_paths)
        self._register_cleanup_paths("prepared_lcu_wads", prepared_bundle_paths)

        logger.info(
            "远端 LCU 最小准备完成：version={}, region={}, bundles={}",
            self.snapshot.version,
            self.ctx.config.game_region,
            len(bundle_cache_paths),
        )
        return LcuPrepareResult(
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
    ) -> BinInputPrepareResult | None:
        """从远端 GAME manifest 提取 `BinUpdater` 所需的 BIN 输入。

        Args:
            reader: 已初始化的数据读取器。
            target: 当前更新目标，取值与 `BinUpdater.update()` 一致。
            champion_ids: 指定英雄 ID 集合。
            map_ids: 指定地图 ID 集合。

        Returns:
            提取结果；若没有任何目标 BIN，返回 `None`。
        """
        extraction_plan = self._build_bin_extraction_plan(
            reader=reader,
            target=target,
            champion_ids=champion_ids,
            map_ids=map_ids,
        )
        if not extraction_plan:
            logger.warning("远端 GAME 快照未规划到任何 BIN 提取目标，已跳过 BIN 输入准备。")
            return None

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
            self._register_cleanup_paths("bin_input_files", extracted_paths)
            self._register_cleanup_paths("bin_input_flags", [flag_file_path])
            logger.info("远端 BIN 输入准备完成：共提取 {} 个文件。", extracted_count)
            return BinInputPrepareResult(
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
    ) -> GameWadPrepareResult | None:
        """准备远端 `extract` 阶段所需的实体 WAD。"""
        wad_paths = self._build_extract_wad_plan(
            reader=reader,
            champion_ids=champion_ids,
            map_ids=map_ids,
            include_champions=include_champions,
            include_maps=include_maps,
        )
        return self._prepare_game_wads(wad_paths)

    def prepare_mapping_wads(
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
    ) -> GameWadPrepareResult | None:
        """准备远端 `mapping` 阶段所需的实体 WAD。"""
        wad_paths = self._build_mapping_wad_plan(
            reader=reader,
            champion_ids=champion_ids,
            map_ids=map_ids,
            include_champions=include_champions,
            include_maps=include_maps,
        )
        return self._prepare_game_wads(wad_paths)

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
    ) -> GameWadPrepareResult | None:
        """为单个实体工作项准备所需 WAD 并集。"""
        wad_paths: set[str] = set()
        if need_extract:
            wad_paths.update(
                self._build_extract_wad_plan(
                    reader=reader,
                    champion_ids=champion_ids,
                    map_ids=map_ids,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )
            )
        if need_mapping:
            wad_paths.update(
                self._build_mapping_wad_plan(
                    reader=reader,
                    champion_ids=champion_ids,
                    map_ids=map_ids,
                    include_champions=include_champions,
                    include_maps=include_maps,
                )
            )
        return self._prepare_game_wads(wad_paths)

    def _ensure_manifest_cached(self, *, manifest_url: str, manifest_cache_dir: Path) -> Path:
        """缓存远端 manifest 文件。"""
        manifest_id = manifest_url.rstrip("/").rsplit("/", maxsplit=1)[-1]
        manifest_path = manifest_cache_dir / manifest_id
        if manifest_path.exists():
            return manifest_path

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        request = Request(manifest_url, headers=REMOTE_MANIFEST_HEADERS)
        with urlopen(request) as response, manifest_path.open("wb") as target:  # noqa: S310
            shutil.copyfileobj(response, target)
        logger.debug(f"已缓存远端 manifest: {manifest_path}")
        return manifest_path

    def _collect_lcu_files(self, manifest: PatcherManifest) -> dict[str, PatcherFile]:
        """收集 LCU 插件目录内的 manifest 文件条目。"""
        lcu_files: dict[str, PatcherFile] = {}
        for file in manifest.files.values():
            relative_path = self._get_lcu_relative_path(file.name)
            if relative_path is None:
                continue
            lcu_files[relative_path.as_posix()] = file
        return lcu_files

    def _find_description_file(self, lcu_files: dict[str, PatcherFile]) -> PatcherFile:
        """定位 `description.json` 文件。"""
        description_file = lcu_files.get(DESCRIPTION_FILE_NAME)
        if description_file is None:
            raise FileNotFoundError("远端 LCU manifest 中缺少 rcp-be-lol-game-data/description.json")
        return description_file

    def _resolve_required_bundle_names(self, description_cache_path: Path) -> list[str]:
        """根据区域与 `description.json` 解析所需 bundle 名称。"""
        description = json.loads(description_cache_path.read_text(encoding="utf-8"))
        riot_meta = description.get("riotMeta")
        if not isinstance(riot_meta, dict):
            raise ValueError(f"description.json 缺少 riotMeta 字段: {description_cache_path}")

        global_bundles = riot_meta.get("globalAssetBundles", [])
        if not isinstance(global_bundles, list):
            raise ValueError("description.json 的 globalAssetBundles 字段类型异常")

        bundle_names = [str(item).strip() for item in global_bundles if str(item).strip()]
        region = self.ctx.config.game_region
        if region != "default":
            per_locale = riot_meta.get("perLocaleAssetBundles", {})
            if not isinstance(per_locale, dict):
                raise ValueError("description.json 的 perLocaleAssetBundles 字段类型异常")

            locale_bundles = (
                per_locale.get(region)
                or per_locale.get(region.lower())
                or per_locale.get(region.upper())
                or []
            )
            if not isinstance(locale_bundles, list):
                raise ValueError(f"description.json 中 {region} 的 bundle 列表类型异常")
            bundle_names.extend(str(item).strip() for item in locale_bundles if str(item).strip())

        deduplicated_names: list[str] = []
        for bundle_name in bundle_names:
            if bundle_name not in deduplicated_names:
                deduplicated_names.append(bundle_name)
        return deduplicated_names

    def _resolve_bundle_files(
        self,
        bundle_names: list[str],
        lcu_files: dict[str, PatcherFile],
    ) -> list[PatcherFile]:
        """把 bundle 文件名映射为 manifest 文件条目。"""
        resolved_files: list[PatcherFile] = []
        missing_names: list[str] = []
        for bundle_name in bundle_names:
            bundle_file = lcu_files.get(bundle_name)
            if bundle_file is None:
                missing_names.append(bundle_name)
                continue
            resolved_files.append(bundle_file)

        if missing_names:
            missing_text = ", ".join(missing_names)
            raise FileNotFoundError(f"远端 LCU manifest 中缺少以下 bundle 文件: {missing_text}")
        return resolved_files

    def _ensure_manifest_files_downloaded(
        self,
        manifest: PatcherManifest,
        files: list[PatcherFile],
    ) -> list[Path]:
        """确保目标文件已下载到缓存目录。"""
        output_paths = [Path(manifest.file_output(file)) for file in files]
        missing_files = [file for file, output_path in zip(files, output_paths, strict=True) if not output_path.exists()]

        if missing_files:
            for output_path in output_paths:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            self._run_coroutine_sync(manifest.download_files_concurrently(missing_files, raise_on_error=True))

        return output_paths

    def _build_bin_extraction_plan(
        self,
        *,
        reader: DataReader,
        target: str,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
    ) -> dict[str, list[str]]:
        """构建远端 BIN 提取计划。"""
        extraction_plan: dict[str, list[str]] = {}

        if champion_ids is not None:
            for champion_id in champion_ids:
                champion = reader.get_champion(champion_id)
                self._extend_champion_bin_plan(extraction_plan, champion)
        elif target in {"skin", "all"}:
            for champion in reader.get_champions():
                self._extend_champion_bin_plan(extraction_plan, champion)

        if map_ids is not None:
            for map_id in map_ids:
                map_data = reader.get_map(map_id)
                self._extend_map_bin_plan(extraction_plan, map_data)
        elif target in {"map", "all"}:
            for map_data in reader.get_maps():
                self._extend_map_bin_plan(extraction_plan, map_data)

        for wad_path, bin_paths in extraction_plan.items():
            extraction_plan[wad_path] = list(dict.fromkeys(bin_paths))
        return {wad_path: bin_paths for wad_path, bin_paths in extraction_plan.items() if bin_paths}

    def _build_extract_wad_plan(
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
    ) -> set[str]:
        """构建 `extract` 阶段所需的 WAD 清单。"""
        include_types = set(self.ctx.config.include_types)
        wad_paths: set[str] = set()

        if champion_ids is not None:
            for champion_id in champion_ids:
                self._extend_extract_wads_for_champion(
                    wad_paths=wad_paths,
                    champion=reader.get_champion(champion_id),
                    champion_banks=reader.get_champion_banks(champion_id),
                    reader=reader,
                    include_types=include_types,
                )
        elif include_champions:
            for champion in reader.get_champions():
                champion_id = champion.get("id")
                if champion_id is None:
                    continue
                self._extend_extract_wads_for_champion(
                    wad_paths=wad_paths,
                    champion=champion,
                    champion_banks=reader.get_champion_banks(int(champion_id)),
                    reader=reader,
                    include_types=include_types,
                )

        if map_ids is not None:
            for map_id in map_ids:
                self._extend_extract_wads_for_map(
                    wad_paths=wad_paths,
                    map_data=reader.get_map(map_id),
                    map_banks=reader.get_map_banks(map_id),
                    reader=reader,
                    include_types=include_types,
                )
        elif include_maps:
            for map_data in reader.get_maps():
                map_id = map_data.get("id")
                if map_id is None:
                    continue
                self._extend_extract_wads_for_map(
                    wad_paths=wad_paths,
                    map_data=map_data,
                    map_banks=reader.get_map_banks(int(map_id)),
                    reader=reader,
                    include_types=include_types,
                )

        return wad_paths

    def _build_mapping_wad_plan(
        self,
        *,
        reader: DataReader,
        champion_ids: tuple[int, ...] | None,
        map_ids: tuple[int, ...] | None,
        include_champions: bool,
        include_maps: bool,
    ) -> set[str]:
        """构建 `mapping` 阶段所需的 WAD 清单。"""
        wad_paths: set[str] = set()

        if champion_ids is not None:
            for champion_id in champion_ids:
                self._extend_mapping_wads_for_champion(
                    wad_paths=wad_paths,
                    champion=reader.get_champion(champion_id),
                    champion_banks=reader.get_champion_banks(champion_id),
                    champion_events=reader.get_champion_events(champion_id),
                    reader=reader,
                )
        elif include_champions:
            for champion in reader.get_champions():
                champion_id = champion.get("id")
                if champion_id is None:
                    continue
                self._extend_mapping_wads_for_champion(
                    wad_paths=wad_paths,
                    champion=champion,
                    champion_banks=reader.get_champion_banks(int(champion_id)),
                    champion_events=reader.get_champion_events(int(champion_id)),
                    reader=reader,
                )

        if map_ids is not None:
            for map_id in map_ids:
                self._extend_mapping_wads_for_map(
                    wad_paths=wad_paths,
                    map_data=reader.get_map(map_id),
                    map_banks=reader.get_map_banks(map_id),
                    map_events=reader.get_map_events(map_id),
                    reader=reader,
                )
        elif include_maps:
            for map_data in reader.get_maps():
                map_id = map_data.get("id")
                if map_id is None:
                    continue
                self._extend_mapping_wads_for_map(
                    wad_paths=wad_paths,
                    map_data=map_data,
                    map_banks=reader.get_map_banks(int(map_id)),
                    map_events=reader.get_map_events(int(map_id)),
                    reader=reader,
                )

        return wad_paths

    @staticmethod
    def _extend_champion_bin_plan(extraction_plan: dict[str, list[str]], champion: dict[str, Any]) -> None:
        """把单个英雄的 BIN 需求追加到提取计划。"""
        wad_root = RemoteSnapshotPreparer._normalize_game_manifest_wad_path(champion.get("wad", {}).get("root"))
        if not wad_root:
            return

        bin_paths: list[str] = []
        for skin in champion.get("skins", []):
            if skin_bin_path := skin.get("binPath"):
                bin_paths.append(str(skin_bin_path))
            for chroma in skin.get("chromas", []):
                if chroma_bin_path := chroma.get("binPath"):
                    bin_paths.append(str(chroma_bin_path))

        if bin_paths:
            extraction_plan.setdefault(str(wad_root), []).extend(bin_paths)

    @staticmethod
    def _extend_extract_wads_for_champion(
        *,
        wad_paths: set[str],
        champion: dict[str, Any],
        champion_banks: dict[str, Any] | None,
        reader: DataReader,
        include_types: set[str],
    ) -> None:
        """根据英雄 banks 数据规划 `extract` 所需 WAD。"""
        if not champion or not champion_banks:
            return

        wad_info = champion.get("wad", {})
        wad_root = str(wad_info.get("root") or "")
        wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
        needs_root = False
        needs_language = False

        for categories in (champion_banks.get("skins") or {}).values():
            for category in categories:
                audio_type = reader.get_audio_type(category)
                if audio_type not in include_types:
                    continue
                if audio_type == "VO":
                    needs_language = True
                else:
                    needs_root = True

        if needs_root and wad_root:
            wad_paths.add(wad_root)
        if needs_language and wad_language:
            wad_paths.add(wad_language)

    @staticmethod
    def _extend_extract_wads_for_map(
        *,
        wad_paths: set[str],
        map_data: dict[str, Any],
        map_banks: dict[str, Any] | None,
        reader: DataReader,
        include_types: set[str],
    ) -> None:
        """根据地图 banks 数据规划 `extract` 所需 WAD。"""
        if not map_data or not map_banks:
            return

        wad_info = map_data.get("wad", {})
        wad_root = str(wad_info.get("root") or "")
        wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
        needs_root = False
        needs_language = False

        for category in (map_banks.get("banks") or {}):
            audio_type = reader.get_audio_type(category)
            if audio_type not in include_types:
                continue
            if audio_type == "VO":
                needs_language = True
            else:
                needs_root = True

        if needs_root and wad_root:
            wad_paths.add(wad_root)
        if needs_language and wad_language:
            wad_paths.add(wad_language)

    @staticmethod
    def _extend_mapping_wads_for_champion(
        *,
        wad_paths: set[str],
        champion: dict[str, Any],
        champion_banks: dict[str, Any] | None,
        champion_events: dict[str, Any] | None,
        reader: DataReader,
    ) -> None:
        """根据英雄 banks/events 数据规划 `mapping` 所需 WAD。"""
        if not champion or not champion_banks or not champion_events:
            return

        wad_info = champion.get("wad", {})
        wad_root = str(wad_info.get("root") or "")
        wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
        needs_root = False
        needs_language = False

        bank_skins = champion_banks.get("skins") or {}
        event_skins = champion_events.get("skins") or {}
        for skin_id, categories in bank_skins.items():
            event_categories = (event_skins.get(skin_id) or {}).get("events", {})
            if not event_categories:
                continue
            for category in categories:
                if not event_categories.get(category):
                    continue
                if "VO" in category:
                    needs_language = True
                else:
                    needs_root = True

        if needs_root and wad_root:
            wad_paths.add(wad_root)
        if needs_language and wad_language:
            wad_paths.add(wad_language)

    @staticmethod
    def _extend_mapping_wads_for_map(
        *,
        wad_paths: set[str],
        map_data: dict[str, Any],
        map_banks: dict[str, Any] | None,
        map_events: dict[str, Any] | None,
        reader: DataReader,
    ) -> None:
        """根据地图 banks/events 数据规划 `mapping` 所需 WAD。"""
        if not map_data or not map_banks or not map_events:
            return

        wad_info = map_data.get("wad", {})
        wad_root = str(wad_info.get("root") or "")
        wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
        needs_root = False
        needs_language = False

        event_categories = map_events.get("events", {})
        for category in (map_banks.get("banks") or {}):
            if not event_categories.get(category):
                continue
            if "VO" in category:
                needs_language = True
            else:
                needs_root = True

        if needs_root and wad_root:
            wad_paths.add(wad_root)
        if needs_language and wad_language:
            wad_paths.add(wad_language)

    @staticmethod
    def _extend_map_bin_plan(extraction_plan: dict[str, list[str]], map_data: dict[str, Any]) -> None:
        """把单个地图的 BIN 需求追加到提取计划。"""
        wad_root = RemoteSnapshotPreparer._normalize_game_manifest_wad_path(map_data.get("wad", {}).get("root"))
        bin_path = map_data.get("binPath")
        if not wad_root or not bin_path:
            return
        extraction_plan.setdefault(str(wad_root), []).append(str(bin_path))

    @staticmethod
    def _normalize_game_manifest_wad_path(wad_root: Any) -> str | None:
        """把本地 `wad.root` 相对路径转换为 GAME manifest 可识别路径。"""
        if not wad_root:
            return None

        raw_path = PurePosixPath(str(wad_root))
        parts = list(raw_path.parts)
        if parts and parts[0].lower() == "game":
            parts = parts[1:]
        if not parts:
            return None
        return PurePosixPath(*parts).as_posix()

    def _prepare_game_wads(self, wad_paths: set[str]) -> GameWadPrepareResult | None:
        """下载并同步远端 GAME WAD 到最小运行目录。"""
        normalized_paths = {
            normalized
            for path in wad_paths
            if (normalized := self._normalize_game_manifest_wad_path(path)) is not None
        }
        if not normalized_paths:
            logger.warning("远端 GAME 快照未规划到任何 WAD 下载目标，已跳过实体 WAD 准备。")
            return None

        manifest_cache_path = self._ensure_manifest_cached(
            manifest_url=self.snapshot.game_manifest_url,
            manifest_cache_dir=self.game_manifest_cache_dir,
        )
        download_root = self.game_cache_root / "downloads"
        manifest = PatcherManifest(file=manifest_cache_path, path=download_root)

        missing_paths = [path for path in sorted(normalized_paths) if path not in manifest.files]
        if missing_paths:
            missing_text = ", ".join(missing_paths)
            raise FileNotFoundError(f"远端 GAME manifest 中缺少以下 WAD 文件: {missing_text}")

        wad_files = [manifest.files[path] for path in sorted(normalized_paths)]
        cached_paths = self._ensure_manifest_files_downloaded(manifest, wad_files)
        prepared_paths = tuple(self._sync_game_file_to_prepared_root(path, download_root) for path in cached_paths)
        self._register_cleanup_paths("cached_game_wads", cached_paths)
        self._register_cleanup_paths("prepared_game_wads", prepared_paths)
        logger.info("远端 GAME WAD 准备完成：共 {} 个文件。", len(prepared_paths))
        return GameWadPrepareResult(
            manifest_cache_path=manifest_cache_path,
            prepared_wad_count=len(prepared_paths),
            prepared_file_paths=prepared_paths,
        )

    def _sync_lcu_file_to_prepared_root(self, source_path: Path) -> Path:
        """把 LCU 缓存文件同步到最小运行目录。"""
        relative_path = self._get_lcu_relative_path(source_path.relative_to(self.download_root).as_posix())
        if relative_path is None:
            raise ValueError(f"无法识别 LCU 相对路径: {source_path}")

        target_path = self.prepared_lcu_root / relative_path
        self._link_or_copy_file(source_path, target_path)
        return target_path

    def _sync_game_file_to_prepared_root(self, source_path: Path, download_root: Path) -> Path:
        """把 GAME 缓存文件同步到最小运行目录。"""
        relative_path = source_path.relative_to(download_root)
        target_path = self.ctx.config.game_path / "Game" / relative_path
        self._link_or_copy_file(source_path, target_path)
        return target_path

    @staticmethod
    def _run_coroutine_sync(coroutine: Any) -> Any:
        """在同步上下文中执行协程。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error["value"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result.get("value")

    @staticmethod
    def _get_lcu_relative_path(file_name: str) -> PurePosixPath | None:
        """提取相对于 `rcp-be-lol-game-data` 根目录的路径。"""
        normalized_parts = [part for part in PurePosixPath(file_name).parts if part not in {".", ""}]
        lowered_parts = [part.lower() for part in normalized_parts]
        suffix_parts = LCU_PLUGIN_SUFFIX.split("/")
        for index in range(len(lowered_parts) - len(suffix_parts) + 1):
            if lowered_parts[index : index + len(suffix_parts)] != suffix_parts:
                continue
            relative_parts = normalized_parts[index + len(suffix_parts) :]
            if not relative_parts:
                return PurePosixPath()
            return PurePosixPath(*relative_parts)
        return None

    @staticmethod
    def _link_or_copy_file(source_path: Path, target_path: Path) -> None:
        """优先硬链接，失败时回退复制。"""
        if target_path.exists():
            return

        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source_path, target_path)
        except OSError:
            shutil.copy2(source_path, target_path)

    def _get_cleanup_registry(self) -> dict[str, set[str]]:
        """获取或初始化远端清理登记表。"""
        registry = self.ctx.runtime_cache.get(REMOTE_CLEANUP_REGISTRY_KEY)
        if isinstance(registry, dict):
            return registry

        registry = {
            "cached_lcu_wads": set(),
            "prepared_lcu_wads": set(),
            "bin_input_files": set(),
            "bin_input_flags": set(),
            "cached_game_wads": set(),
            "prepared_game_wads": set(),
        }
        self.ctx.runtime_cache[REMOTE_CLEANUP_REGISTRY_KEY] = registry
        return registry

    def _register_cleanup_paths(self, key: str, paths: list[Path] | tuple[Path, ...]) -> None:
        """登记可清理文件路径。"""
        registry = self._get_cleanup_registry()
        registry[key].update(str(path) for path in paths)

    @staticmethod
    def _remove_registered_paths(paths: set[str], *, dry_run: bool) -> int:
        """删除或统计已登记路径数量。"""
        removed_count = 0
        for raw_path in list(paths):
            path = Path(raw_path)
            if dry_run:
                if path.exists():
                    removed_count += 1
                continue
            try:
                if path.exists():
                    path.unlink()
                    removed_count += 1
            except OSError:
                logger.warning(f"清理远端产物失败: {path}")
            finally:
                paths.discard(raw_path)
        return removed_count

    @staticmethod
    def _prune_empty_tree(root: Path) -> None:
        """删除根目录下的空目录。"""
        if not root.exists():
            return

        for current_root, _, _ in os.walk(root, topdown=False):
            current_path = Path(current_root)
            try:
                if any(current_path.iterdir()):
                    continue
            except OSError:
                continue
            try:
                current_path.rmdir()
            except OSError:
                continue
