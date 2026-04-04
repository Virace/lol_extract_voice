"""远端 GAME manifest、WAD 计划与准备辅助函数。"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger

from lol_audio_unpack.app.targets import iter_entity_refs


def build_bin_plan(
    *,
    reader: Any,
    target: str,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
) -> dict[str, list[str]]:
    """构建远端 BIN 提取计划。

    Args:
        reader: 数据读取器。
        target: 当前更新目标。
        champion_ids: 指定英雄 ID 集合。
        map_ids: 指定地图 ID 集合。

    Returns:
        WAD 到 BIN 相对路径列表的映射。
    """
    extraction_plan: dict[str, list[str]] = {}
    include_champions = target in {"skin", "all"}
    include_maps = target in {"map", "all"}

    for entity_type, entity_id in iter_entity_refs(
        reader,
        champion_ids=champion_ids,
        map_ids=map_ids,
        include_champions=include_champions,
        include_maps=include_maps,
    ):
        if entity_type == "champion":
            champion = reader.get_champion(entity_id)
            add_champion_bins(extraction_plan, champion)
            continue
        if entity_type == "map":
            map_data = reader.get_map(entity_id)
            add_map_bins(extraction_plan, map_data)
            continue

    for wad_path, bin_paths in extraction_plan.items():
        extraction_plan[wad_path] = list(dict.fromkeys(bin_paths))
    return {wad_path: bin_paths for wad_path, bin_paths in extraction_plan.items() if bin_paths}


def build_extract_plan(
    *,
    reader: Any,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
    include_champions: bool,
    include_maps: bool,
) -> set[str]:
    """构建 `extract` 阶段所需的 WAD 清单。

    Args:
        reader: 数据读取器。
        champion_ids: 指定英雄 ID 集合。
        map_ids: 指定地图 ID 集合。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。
    Returns:
        需要准备的 WAD 路径集合。
    """
    include_types = set(reader.ctx.config.include_types)
    wad_paths: set[str] = set()

    for entity_type, entity_id in iter_entity_refs(
        reader,
        champion_ids=champion_ids,
        map_ids=map_ids,
        include_champions=include_champions,
        include_maps=include_maps,
    ):
        if entity_type == "champion":
            add_champion_extract_wads(
                wad_paths=wad_paths,
                champion=reader.get_champion(entity_id),
                champion_banks=reader.get_champion_banks(entity_id),
                reader=reader,
                include_types=include_types,
            )
            continue
        if entity_type == "map":
            add_map_extract_wads(
                wad_paths=wad_paths,
                map_data=reader.get_map(entity_id),
                map_banks=reader.get_map_banks(entity_id),
                reader=reader,
                include_types=include_types,
            )
    return wad_paths


def build_mapping_plan(
    *,
    reader: Any,
    champion_ids: tuple[int, ...] | None,
    map_ids: tuple[int, ...] | None,
    include_champions: bool,
    include_maps: bool,
) -> set[str]:
    """构建 `mapping` 阶段所需的 WAD 清单。

    Args:
        reader: 数据读取器。
        champion_ids: 指定英雄 ID 集合。
        map_ids: 指定地图 ID 集合。
        include_champions: 是否包含英雄。
        include_maps: 是否包含地图。

    Returns:
        需要准备的 WAD 路径集合。
    """
    wad_paths: set[str] = set()

    for entity_type, entity_id in iter_entity_refs(
        reader,
        champion_ids=champion_ids,
        map_ids=map_ids,
        include_champions=include_champions,
        include_maps=include_maps,
    ):
        if entity_type == "champion":
            add_champion_mapping_wads(
                wad_paths=wad_paths,
                champion=reader.get_champion(entity_id),
                champion_banks=reader.get_champion_banks(entity_id),
                champion_events=reader.get_champion_events(entity_id),
                reader=reader,
            )
            continue
        if entity_type == "map":
            add_map_mapping_wads(
                wad_paths=wad_paths,
                map_data=reader.get_map(entity_id),
                map_banks=reader.get_map_banks(entity_id),
                map_events=reader.get_map_events(entity_id),
                reader=reader,
            )

    return wad_paths


def add_champion_bins(extraction_plan: dict[str, list[str]], champion: dict[str, Any]) -> None:
    """把单个英雄的 BIN 需求追加到提取计划。

    Args:
        extraction_plan: 当前提取计划。
        champion: 英雄数据。
    """
    wad_root = normalize_wad_path(champion.get("wad", {}).get("root"))
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


def add_champion_extract_wads(
    *,
    wad_paths: set[str],
    champion: dict[str, Any],
    champion_banks: dict[str, Any] | None,
    reader: Any,
    include_types: set[str],
) -> None:
    """根据英雄 banks 数据规划 `extract` 所需 WAD。

    Args:
        wad_paths: 当前 WAD 路径集合。
        champion: 英雄数据。
        champion_banks: 英雄 banks 数据。
        reader: 数据读取器。
        include_types: 当前启用的音频类型集合。
    """
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


def add_map_extract_wads(
    *,
    wad_paths: set[str],
    map_data: dict[str, Any],
    map_banks: dict[str, Any] | None,
    reader: Any,
    include_types: set[str],
) -> None:
    """根据地图 banks 数据规划 `extract` 所需 WAD。

    Args:
        wad_paths: 当前 WAD 路径集合。
        map_data: 地图数据。
        map_banks: 地图 banks 数据。
        reader: 数据读取器。
        include_types: 当前启用的音频类型集合。
    """
    if not map_data or not map_banks:
        return

    wad_info = map_data.get("wad", {})
    wad_root = str(wad_info.get("root") or "")
    wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
    needs_root = False
    needs_language = False

    for category in map_banks.get("banks") or {}:
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


def add_champion_mapping_wads(
    *,
    wad_paths: set[str],
    champion: dict[str, Any],
    champion_banks: dict[str, Any] | None,
    champion_events: dict[str, Any] | None,
    reader: Any,
) -> None:
    """根据英雄 banks/events 数据规划 `mapping` 所需 WAD。

    Args:
        wad_paths: 当前 WAD 路径集合。
        champion: 英雄数据。
        champion_banks: 英雄 banks 数据。
        champion_events: 英雄 events 数据。
        reader: 数据读取器。
    """
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


def add_map_mapping_wads(
    *,
    wad_paths: set[str],
    map_data: dict[str, Any],
    map_banks: dict[str, Any] | None,
    map_events: dict[str, Any] | None,
    reader: Any,
) -> None:
    """根据地图 banks/events 数据规划 `mapping` 所需 WAD。

    Args:
        wad_paths: 当前 WAD 路径集合。
        map_data: 地图数据。
        map_banks: 地图 banks 数据。
        map_events: 地图 events 数据。
        reader: 数据读取器。
    """
    if not map_data or not map_banks or not map_events:
        return

    wad_info = map_data.get("wad", {})
    wad_root = str(wad_info.get("root") or "")
    wad_language = str(wad_info.get(reader.ctx.config.game_region) or "")
    needs_root = False
    needs_language = False

    event_categories = map_events.get("events", {})
    for category in map_banks.get("banks") or {}:
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


def add_map_bins(extraction_plan: dict[str, list[str]], map_data: dict[str, Any]) -> None:
    """把单个地图的 BIN 需求追加到提取计划。

    Args:
        extraction_plan: 当前提取计划。
        map_data: 地图数据。
    """
    wad_root = normalize_wad_path(map_data.get("wad", {}).get("root"))
    bin_path = map_data.get("binPath")
    if not wad_root or not bin_path:
        return
    extraction_plan.setdefault(str(wad_root), []).append(str(bin_path))


def normalize_wad_path(wad_root: Any) -> str | None:
    """把本地 `wad.root` 相对路径转换为 GAME manifest 可识别路径。

    Args:
        wad_root: 原始 WAD 根路径。

    Returns:
        GAME manifest 可识别的相对路径；无法转换时返回 `None`。
    """
    if not wad_root:
        return None

    raw_path = PurePosixPath(str(wad_root))
    parts = list(raw_path.parts)
    if parts and parts[0].lower() == "game":
        parts = parts[1:]
    if not parts:
        return None
    return PurePosixPath(*parts).as_posix()


def prepare_wads(
    *,
    preparer: Any,
    wad_paths: set[str],
    manifest_class: type[Any],
    result_class: type[Any],
) -> Any:
    """下载并同步远端 GAME WAD 到最小运行目录。

    Args:
        preparer: 当前远端准备器实例。
        wad_paths: 原始 WAD 路径集合。
        manifest_class: 需要构造的 manifest 类型。
        result_class: 结果对象类型。

    Returns:
        `GameWadResult` 或 `None`。
    """
    normalized_paths = {normalized for path in wad_paths if (normalized := normalize_wad_path(path)) is not None}
    if not normalized_paths:
        logger.warning("远端 GAME 快照未规划到任何 WAD 下载目标，已跳过实体 WAD 准备。")
        return None

    manifest_cache_path = preparer._ensure_manifest_cached(
        manifest_url=preparer.snapshot.game_manifest_url,
        manifest_cache_dir=preparer.game_manifest_cache_dir,
    )
    download_root = preparer.game_cache_root / "downloads"
    manifest = manifest_class(file=manifest_cache_path, path=download_root)

    missing_paths = [path for path in sorted(normalized_paths) if path not in manifest.files]
    if missing_paths:
        missing_text = ", ".join(missing_paths)
        raise FileNotFoundError(f"远端 GAME manifest 中缺少以下 WAD 文件: {missing_text}")

    wad_files = [manifest.files[path] for path in sorted(normalized_paths)]
    cached_paths = preparer._ensure_files_downloaded(manifest, wad_files)
    prepared_paths = tuple(preparer._sync_game_file(path, download_root) for path in cached_paths)
    preparer._track_cleanup_paths("cached_game_wads", cached_paths)
    preparer._track_cleanup_paths("prepared_game_wads", prepared_paths)
    logger.info("远端 GAME WAD 准备完成：共 {} 个文件。", len(prepared_paths))
    return result_class(
        manifest_cache_path=manifest_cache_path,
        prepared_wad_count=len(prepared_paths),
        prepared_file_paths=prepared_paths,
    )
