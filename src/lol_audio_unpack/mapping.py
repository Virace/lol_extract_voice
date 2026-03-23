"""音频事件映射核心流程。"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools import WAD, AudioEventMapper, NativeHIRC, WwiserHIRC, WwiserManager
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.utils import create_metadata_object, write_data
from lol_audio_unpack.model import AudioEntityData, generate_champion_tasks, generate_map_tasks
from lol_audio_unpack.utils.logging import performance_monitor

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


ParsedHIRC = NativeHIRC | WwiserHIRC


def _get_wwiser_path(ctx: AppContext) -> Path | str | None:
    """获取 wwiser 可执行路径。"""
    return ctx.config.wwiser_path


def _resolve_wwiser_path(ctx: AppContext) -> Path | None:
    """解析并校验 wwiser 可执行路径。"""
    wwiser_path = _get_wwiser_path(ctx)
    if wwiser_path is None:
        return None

    path = Path(wwiser_path)
    if not path.is_file():
        raise ValueError(f"错误：Wwiser 工具路径不存在或不是文件: {path}")
    return path


def describe_hirc_backend(ctx: AppContext) -> str:
    """返回当前 mapping 流程使用的 HIRC 后端描述。"""
    wwiser_path = _resolve_wwiser_path(ctx)
    if wwiser_path is None:
        return "NativeHIRC（默认）"
    return f"WwiserHIRC ({wwiser_path})"


def _create_wwiser_manager(ctx: AppContext) -> WwiserManager | None:
    """按上下文创建可选的 wwiser 管理器。"""
    wwiser_path = _resolve_wwiser_path(ctx)
    if wwiser_path is None:
        return None
    return WwiserManager(wwiser_path)


def _get_cache_base_path(ctx: AppContext) -> Path:
    """获取 cache 根目录。"""
    return Path(ctx.paths.cache_path)


def _get_hash_base_path(ctx: AppContext) -> Path:
    """获取 hashes 根目录。"""
    return Path(ctx.paths.hash_path)


def _get_game_base_path(ctx: AppContext) -> Path:
    """获取游戏根目录。"""
    return Path(ctx.config.game_path)


@dataclass
class MappingRuntimeCache:
    """映射流程中的运行时缓存。"""

    wad_cache: dict[Path, WAD] = field(default_factory=dict)
    extract_cache: set[tuple[Path, str]] = field(default_factory=set)
    hirc_cache: dict[tuple[Path, str], ParsedHIRC] = field(default_factory=dict)
    cache_lock: threading.Lock | None = None


def _get_wad_instance(
    wad_path: Path,
    runtime_cache: MappingRuntimeCache | None,
) -> WAD:
    """获取 WAD 实例并复用运行时缓存。

    Args:
        wad_path: WAD 文件绝对路径。
        runtime_cache: 映射过程共享缓存；为 ``None`` 时不使用缓存。

    Returns:
        对应路径的 ``WAD`` 实例。
    """
    if runtime_cache is None:
        return WAD(wad_path)

    wad_cache = runtime_cache.wad_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        if wad_path not in wad_cache:
            wad_cache[wad_path] = WAD(wad_path)
        return wad_cache[wad_path]

    with cache_lock:
        if wad_path not in wad_cache:
            wad_cache[wad_path] = WAD(wad_path)
        return wad_cache[wad_path]


def _is_bnk_extracted(
    key: tuple[Path, str],
    runtime_cache: MappingRuntimeCache | None,
) -> bool:
    """检查 bnk 文件是否已在本轮执行中提取过。

    Args:
        key: 提取去重键，格式为 ``(wad_path, bnk_rel_path)``。
        runtime_cache: 映射过程共享缓存。

    Returns:
        ``True`` 表示已提取过，``False`` 表示未提取。
    """
    if runtime_cache is None:
        return False
    extract_cache = runtime_cache.extract_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        return key in extract_cache
    with cache_lock:
        return key in extract_cache


def _mark_bnk_extracted(
    key: tuple[Path, str],
    runtime_cache: MappingRuntimeCache | None,
) -> None:
    """标记 bnk 文件已提取。

    Args:
        key: 提取去重键，格式为 ``(wad_path, bnk_rel_path)``。
        runtime_cache: 映射过程共享缓存。
    """
    if runtime_cache is None:
        return
    extract_cache = runtime_cache.extract_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        extract_cache.add(key)
        return
    with cache_lock:
        extract_cache.add(key)


def _get_cached_hirc(
    bnk_path: Path,
    hirc_cache_dir: Path,
    wwiser_manager: WwiserManager | None,
    runtime_cache: MappingRuntimeCache | None,
) -> ParsedHIRC:
    """获取 HIRC 对象并复用缓存。

    Args:
        bnk_path: bnk 文件路径。
        hirc_cache_dir: hirc 缓存目录。
        wwiser_manager: 可选的 wwiser 管理器；为 ``None`` 时走 ``NativeHIRC``。
        runtime_cache: 映射过程共享缓存。

    Returns:
        解析后的 HIRC 对象。
    """
    backend_key = "wwiser" if wwiser_manager is not None else "native"
    cache_key = (bnk_path, backend_key)

    def parse_hirc() -> ParsedHIRC:
        if wwiser_manager is None:
            return NativeHIRC.from_bnk(bnk_path, cache_dir=hirc_cache_dir)
        return WwiserHIRC.from_bnk(bnk_path, cache_dir=hirc_cache_dir, wwiser_manager=wwiser_manager)

    if runtime_cache is None:
        return parse_hirc()

    hirc_cache = runtime_cache.hirc_cache
    cache_lock = runtime_cache.cache_lock

    if cache_lock is None:
        cached = hirc_cache.get(cache_key)
        if cached is not None:
            return cached
        parsed = parse_hirc()
        hirc_cache[cache_key] = parsed
        return parsed

    with cache_lock:
        cached = hirc_cache.get(cache_key)
    if cached is not None:
        return cached

    parsed = parse_hirc()
    with cache_lock:
        existing = hirc_cache.get(cache_key)
        if existing is not None:
            return existing
        hirc_cache[cache_key] = parsed
        return parsed


@logger.catch
@performance_monitor(level="DEBUG")
def build_audio_event_mapping(  # noqa: PLR0913
    entity_data: AudioEntityData,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: MappingRuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个实体的事件映射。

    Args:
        entity_data: 包含 events 的实体数据。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器；为 ``None`` 时按 ``ctx`` 自动选择后端。
        integrate_data: 是否输出整合数据（实体信息 + banks + mapping）。
        runtime_cache: 映射流程共享缓存，用于复用 WAD/HIRC 解析结果。
        ctx: 运行时上下文。

    Returns:
        映射结果或整合结果字典。

    Raises:
        ValueError: 实体没有可用 events 数据时抛出。
    """
    if not entity_data.events:
        raise ValueError(f"{entity_data.entity_name} 缺少事件数据，请使用 include_events=True 创建实体数据")

    logger.info(f"构建 {entity_data.entity_name} (ID:{entity_data.entity_id}) 的事件映射")

    # 使用传入的 wwiser_manager，或按上下文决定是否启用 WwiserHIRC。
    if wwiser_manager is None:
        wm = _create_wwiser_manager(ctx)
    else:
        wm = wwiser_manager

    # 创建版本化的缓存目录
    version_cache_dir = _get_cache_base_path(ctx) / reader.version
    version_hash_dir = _get_hash_base_path(ctx) / reader.version
    version_cache_dir.mkdir(parents=True, exist_ok=True)
    version_hash_dir.mkdir(parents=True, exist_ok=True)

    # 创建映射文件保存目录
    entity_type_plural = "champions" if entity_data.entity_type == "champion" else "maps"
    mapping_save_dir = version_hash_dir / entity_type_plural
    mapping_save_dir.mkdir(parents=True, exist_ok=True)

    # 准备结果数据结构，参考 bin_updater 的 _create_base_data 实现
    base_data = create_metadata_object(reader.version, reader.get_languages())  # 映射文件不需要语言信息

    # 添加实体特定信息
    if entity_data.entity_type == "champion":
        base_data["championId"] = entity_data.entity_id
        base_data["alias"] = entity_data.entity_alias
        base_data["skins"] = {}  # 英雄使用 skins 字段
        mapping_data_key = "skins"
    elif entity_data.entity_type == "map":
        base_data["mapId"] = entity_data.entity_id
        base_data["name"] = entity_data.entity_alias  # 地图使用 name 而不是 alias
        base_data["map"] = {}  # 地图使用 map 字段
        mapping_data_key = "map"

    mapping_result = base_data
    mapped_event_count = 0
    errored_event_count = 0
    skipped_event_count = 0

    # 遍历所有子实体（皮肤或地图）
    for sub_id, sub_data in entity_data.sub_entities.items():
        banks_data = sub_data["categories"]
        events_data = entity_data.events.get(sub_id, {}).get("events", {})

        if not events_data:
            logger.debug(f"子实体 {sub_id} 无事件数据，跳过")
            continue

        sub_mapping = {}

        # 遍历每个音频类别
        for category, paths_list in banks_data.items():
            event_list = events_data.get(category, [])
            if not event_list:
                logger.debug(f"类别 {category} 无事件列表，跳过")
                continue

            logger.debug(f"处理类别: {category}")

            # 处理多个路径组合的情况（特殊情况需要合并）
            if len(paths_list) > 1:
                logger.info(f"特殊情况，{sub_id} {category} 有 {len(paths_list)} 个路径组合，将逐个处理并合并")

            category_mapping = None  # 用于合并多个映射结果
            category_error_count = 0

            # 循环处理每个路径组合
            for path_group_idx, path_group in enumerate(paths_list):
                logger.debug(f"处理路径组合 {path_group_idx + 1}/{len(paths_list)}: {path_group}")

                # 获取 _events.bnk 文件路径
                bnk_paths = [path for path in path_group if path.endswith("_events.bnk")]
                if len(bnk_paths) != 1:
                    if len(bnk_paths) == 0:
                        logger.debug(f"路径组合 {path_group_idx + 1} 无 events.bnk 文件，跳过")
                        continue
                    else:
                        logger.warning(f"路径组合 {path_group_idx + 1} 的 events.bnk 文件数量异常: {len(bnk_paths)}")
                        continue

                # 确定使用哪个WAD文件
                if "VO" in category:
                    wad_file = entity_data.wad_language
                    if not wad_file:
                        logger.warning(f"VO类别但无语言WAD文件: {category}")
                        continue
                else:
                    wad_file = entity_data.wad_root

                wad_path = _get_game_base_path(ctx) / wad_file
                if not wad_path.exists():
                    logger.warning(f"WAD文件不存在: {wad_path}")
                    continue

                try:
                    wad_obj = _get_wad_instance(wad_path, runtime_cache=runtime_cache)
                    # 提取 events.bnk 文件到版本化缓存目录
                    bnk_rel_path = bnk_paths[0]
                    extract_key = (wad_path, bnk_rel_path)
                    if not _is_bnk_extracted(extract_key, runtime_cache=runtime_cache):
                        wad_obj.extract(bnk_paths, out_dir=version_cache_dir)
                        _mark_bnk_extracted(extract_key, runtime_cache=runtime_cache)

                    bnk_path = version_cache_dir / bnk_rel_path
                    if not bnk_path.exists():
                        logger.warning(f"提取的BNK文件不存在: {bnk_path}")
                        continue

                    # 使用版本化的hirc缓存目录
                    hirc_cache_dir = version_cache_dir / "hirc"
                    hirc_cache_dir.mkdir(parents=True, exist_ok=True)

                    # 默认走 NativeHIRC；仅在显式提供 wwiser 路径时走 WwiserHIRC。
                    hirc = _get_cached_hirc(
                        bnk_path=bnk_path,
                        hirc_cache_dir=hirc_cache_dir,
                        wwiser_manager=wm,
                        runtime_cache=runtime_cache,
                    )

                    # 创建映射并构建AudioMapping对象
                    current_mapper = AudioEventMapper(event_list, hirc)
                    current_mapping = current_mapper.build_mapping()

                    # 合并映射结果
                    if category_mapping is None:
                        # 第一个映射，直接使用
                        category_mapping = current_mapping
                        logger.debug(f"路径组合 {path_group_idx + 1}: 创建基础映射，事件数: {len(event_list)}")
                    else:
                        # 后续映射，需要合并到已有的AudioMapping对象
                        category_mapping.merge_with(current_mapping)
                        logger.debug(f"路径组合 {path_group_idx + 1}: 合并映射完成")

                except Exception as e:
                    category_error_count += 1
                    logger.error(f"处理路径组合 {path_group_idx + 1} 时出错: {e}")
                    logger.debug(traceback.format_exc())
                    continue

            # 保存最终的合并结果
            if category_mapping is not None:
                # 检查映射结果是否为空，只保存非空的映射
                if category_mapping.forward_mapping:
                    mapped_count = len(category_mapping.forward_mapping)
                    skipped_count = max(len(event_list) - mapped_count, 0)
                    mapped_event_count += mapped_count
                    skipped_event_count += skipped_count
                    sub_mapping[category] = category_mapping.forward_mapping
                    logger.debug(
                        f"完成 {category} 的映射，处理了 {len(paths_list)} 个路径组合，事件数: {len(event_list)}，"
                        f"映射条目: {mapped_count}，未映射跳过: {skipped_count}"
                    )
                else:
                    skipped_event_count += len(event_list)
                    logger.warning(f"类别 {category} 映射结果为空，跳过保存")
            else:
                if category_error_count > 0:
                    errored_event_count += len(event_list)
                else:
                    skipped_event_count += len(event_list)
                logger.warning(f"类别 {category} 没有生成任何有效的映射结果")

        # 只保存非空的子实体映射
        if sub_mapping:
            mapping_result[mapping_data_key][sub_id] = {"events": sub_mapping}
            logger.debug(f"子实体 {sub_id} 保存了 {len(sub_mapping)} 个有效类别的映射")
        else:
            logger.debug(f"子实体 {sub_id} 无有效映射数据，跳过保存")

    # 如果需要整合数据，则进行数据整合处理
    if integrate_data:
        integrated_result = integrate_entity_data(entity_data, reader, mapping_result)

        # 保存整合数据到文件
        if integrated_result and integrated_result.get("data", {}).get(
            "skins" if entity_data.entity_type == "champion" else "map"
        ):
            integration_save_dir = (
                version_hash_dir / "integrated" / ("champions" if entity_data.entity_type == "champion" else "maps")
            )
            integration_save_dir.mkdir(parents=True, exist_ok=True)
            integration_file_base = integration_save_dir / entity_data.entity_id
            write_data(integrated_result, integration_file_base, dev_mode=ctx.config.dev_mode)
            logger.debug(f"整合数据已保存: {integration_file_base}")

        logger.success(
            f"{entity_data.entity_name} 的整合数据统计：成功映射事件 {mapped_event_count} 个，"
            f"异常事件 {errored_event_count} 个，未映射跳过 {skipped_event_count} 个"
        )
        return integrated_result
    else:
        # 移除 languages 字段（映射文件不需要）
        if "metadata" in mapping_result and "languages" in mapping_result["metadata"]:
            del mapping_result["metadata"]["languages"]
        # 保存映射结果到文件
        if mapping_result[mapping_data_key]:
            mapping_file_base = mapping_save_dir / entity_data.entity_id
            write_data(mapping_result, mapping_file_base, dev_mode=ctx.config.dev_mode)
            logger.debug(f"映射结果已保存: {mapping_file_base}")
        else:
            logger.warning(f"{entity_data.entity_name} 没有找到任何有效映射数据")

        logger.success(
            f"{entity_data.entity_name} 的事件映射统计：成功映射事件 {mapped_event_count} 个，"
            f"异常事件 {errored_event_count} 个，未映射跳过 {skipped_event_count} 个"
        )
        return mapping_result


def integrate_entity_data(
    entity_data: AudioEntityData, reader: DataReader, mapping_result: dict[str, Any]
) -> dict[str, Any]:
    """整合实体数据，将banks、events和mapping数据合并到完整的实体数据结构中

    :param entity_data: 音频实体数据
    :param reader: 数据读取器实例
    :param mapping_result: 映射结果数据
    :returns: 整合后的完整实体数据
    """
    logger.info(f"开始整合 {entity_data.entity_name} 的数据")

    # 获取实体的完整数据
    if entity_data.entity_type == "champion":
        entity_info = reader.get_champion(int(entity_data.entity_id))
        banks_data = reader.get_champion_banks(int(entity_data.entity_id))
        data_key = "skins"
    else:  # map
        entity_info = reader.get_map(int(entity_data.entity_id))
        banks_data = reader.get_map_banks(int(entity_data.entity_id))
        data_key = "map"

    if not entity_info or not banks_data:
        logger.warning(f"无法获取 {entity_data.entity_name} 的完整数据信息")
        return {}

    # 创建基础整合数据结构，只有metadata和data两个根键
    integrated_data = {"metadata": mapping_result.get("metadata", {}), "data": {}}

    # 添加wad信息
    wad_info = {"root": entity_data.wad_root}
    if entity_data.wad_language:
        wad_info["language"] = entity_data.wad_language

    # 添加实体特定信息到data字段下
    if entity_data.entity_type == "champion":
        integrated_data["data"].update(
            {
                "championId": entity_data.entity_id,
                "alias": entity_data.entity_alias,
                "id": entity_info["id"],
                "names": entity_info.get("names", {}),
                "titles": entity_info.get("titles", {}),
                "descriptions": entity_info.get("descriptions", {}),
                "wad": wad_info,
                "skins": [],
            }
        )
        skins_list = entity_info.get("skins", [])
    else:  # map
        integrated_data["data"].update(
            {
                "mapId": entity_data.entity_id,
                "name": entity_data.entity_alias,
                "id": entity_info["id"],
                "names": entity_info.get("names", {}),
                "descriptions": entity_info.get("descriptions", {}),
                "wad": wad_info,
                "map": {},
            }
        )
        # 地图数据结构不同，直接处理单个地图
        skins_list = [{"id": int(entity_data.entity_id)}]

    # 获取mapping结果中的数据
    mapping_data = mapping_result.get(data_key, {})

    # 处理每个皮肤/地图
    processed_skins = []
    for skin_info in skins_list:
        skin_id = str(skin_info["id"])

        # 检查该皮肤是否在mapping结果中（只保留有事件数据的皮肤）
        if skin_id not in mapping_data:
            logger.debug(f"皮肤/地图 {skin_id} 没有事件数据，跳过")
            continue

        # 构建皮肤的整合数据，按照指定顺序：id -> isBase -> skinNames -> binPath -> events
        skin_integrated = {"id": skin_info["id"]}

        # 添加皮肤特定信息
        if entity_data.entity_type == "champion":
            skin_integrated.update(
                {
                    "isBase": skin_info.get("isBase", False),
                    "skinNames": skin_info.get("skinNames", {}),
                    "binPath": skin_info.get("binPath", ""),
                }
            )

        # 最后添加events字段
        skin_integrated["events"] = {}

        # 获取banks数据和mapping数据
        skin_banks = (
            banks_data.get("skins", {}).get(skin_id, {})
            if entity_data.entity_type == "champion"
            else banks_data.get("banks", {})
        )
        skin_mapping = mapping_data.get(skin_id, {}).get("events", {})

        # 处理每个音频类别
        for category in skin_mapping.keys():
            banks_paths = skin_banks.get(category, [])
            mapping_events = skin_mapping.get(category, {})

            if banks_paths and mapping_events:
                skin_integrated["events"][category] = {"banks": banks_paths, "mapping": mapping_events}

        # 只添加有事件数据的皮肤
        if skin_integrated["events"]:
            processed_skins.append(skin_integrated)
            logger.debug(f"皮肤/地图 {skin_id} 整合完成，包含 {len(skin_integrated['events'])} 个音频类别")

    # 保存处理后的皮肤数据到data字段下
    if entity_data.entity_type == "champion":
        integrated_data["data"]["skins"] = processed_skins
    elif processed_skins:
        # 地图只有一个，直接保存到map字段
        integrated_data["data"]["map"] = processed_skins[0]

    logger.success(f"整合完成，{entity_data.entity_name} 包含 {len(processed_skins)} 个有效皮肤/地图数据")
    return integrated_data


def build_champion_mapping(  # noqa: PLR0913
    champion_id: int,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: MappingRuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个英雄的事件映射。

    Args:
        champion_id: 英雄 ID。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器；为 ``None`` 时按 ``ctx`` 自动选择后端。
        integrate_data: 是否输出整合数据。
        runtime_cache: 映射流程共享缓存。
        ctx: 运行时上下文。

    Returns:
        英雄映射结果；失败时返回空字典。
    """
    try:
        # 创建包含事件数据的AudioEntityData实例
        entity_data = AudioEntityData.from_champion(champion_id, reader, include_events=True, ctx=ctx)
        # 构建映射
        return build_audio_event_mapping(
            entity_data,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
    except ValueError as e:
        logger.error(str(e))
        return {}


def build_map_mapping(  # noqa: PLR0913
    map_id: int,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: MappingRuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个地图的事件映射。

    Args:
        map_id: 地图 ID。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器；为 ``None`` 时按 ``ctx`` 自动选择后端。
        integrate_data: 是否输出整合数据。
        runtime_cache: 映射流程共享缓存。
        ctx: 运行时上下文。

    Returns:
        地图映射结果；失败时返回空字典。
    """
    try:
        # 创建包含事件数据的AudioEntityData实例
        entity_data = AudioEntityData.from_map(map_id, reader, include_events=True, ctx=ctx)
        # 构建映射
        return build_audio_event_mapping(
            entity_data,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
    except ValueError as e:
        logger.error(str(e))
        return {}


def execute_mapping_tasks(  # noqa: PLR0913
    tasks: list[tuple[str, int, str]],
    reader: DataReader,
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """执行映射任务集

    :param tasks: 任务元组列表 [("entity_type", id, description), ...]
    :param reader: 数据读取器
    :param max_workers: 最大工作线程数
    :param integrate_data: 是否生成整合数据
    :param ctx: 运行时上下文。
    """
    if not tasks:
        logger.warning("没有任何任务需要执行")
        return

    start_time = time.time()
    total_tasks = len(tasks)

    # 统计任务类型
    champion_count = sum(1 for entity_type, _, _ in tasks if entity_type == "champion")
    map_count = sum(1 for entity_type, _, _ in tasks if entity_type == "map")

    summary_parts = []
    if champion_count > 0:
        summary_parts.append(f"{champion_count} 个英雄")
    if map_count > 0:
        summary_parts.append(f"{map_count} 个地图")
    totals_by_type = {
        "champion": champion_count,
        "map": map_count,
    }
    finished_by_type = {
        "champion": 0,
        "map": 0,
    }

    logger.info(
        f"开始构建 {total_tasks} 个实体的事件映射 ({' 和 '.join(summary_parts)})，"
        f"模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )
    logger.info(f"HIRC 后端: {describe_hirc_backend(ctx)}")

    # 初始化共享的可选 wwiser 管理器，避免重复创建。
    wwiser_manager = _create_wwiser_manager(ctx)
    runtime_cache = MappingRuntimeCache(cache_lock=threading.Lock() if max_workers > 1 else None)

    def build_entity_mapping(entity_type: str, entity_id: int) -> None:
        """构建单个实体映射的辅助函数"""
        if entity_type == "champion":
            build_champion_mapping(
                entity_id,
                reader,
                wwiser_manager,
                integrate_data,
                runtime_cache=runtime_cache,
                ctx=ctx,
            )
        elif entity_type == "map":
            build_map_mapping(
                entity_id,
                reader,
                wwiser_manager,
                integrate_data,
                runtime_cache=runtime_cache,
                ctx=ctx,
            )
        else:
            raise ValueError(f"未知的实体类型: {entity_type}")

    if max_workers > 1:
        # --- 多线程模式 ---
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(build_entity_mapping, entity_type, entity_id): (entity_type, entity_id, description)
                for entity_type, entity_id, description in tasks
            }
            completed_count = 0

            for future in as_completed(future_to_task):
                entity_type, entity_id, description = future_to_task[future]
                completed_count += 1
                finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1

                try:
                    future.result()  # 获取结果，如果函数中出现异常，这里会重新抛出
                    progress_message = f"{description} 映射完成"
                    logger.info(f"进度: {completed_count}/{total_tasks} - {progress_message}。")
                except Exception as exc:
                    progress_message = f"{description} 映射失败"
                    logger.error(f"{description} 映射时发生错误: {exc}")
                    logger.debug(traceback.format_exc())
                if progress_callback is not None:
                    progress_callback(
                        entity_type,
                        finished_by_type.get(entity_type, completed_count),
                        max(totals_by_type.get(entity_type, total_tasks), 1),
                        progress_message,
                    )
    else:
        # --- 单线程模式 ---
        completed_count = 0
        for entity_type, entity_id, description in tasks:
            try:
                build_entity_mapping(entity_type, entity_id)
                progress_message = f"{description} 映射完成"
                completed_count += 1
                logger.info(f"进度: {completed_count}/{total_tasks} - {progress_message}。")
            except Exception as exc:
                progress_message = f"{description} 映射失败"
                logger.error(f"{description} 映射时发生错误: {exc}")
                logger.debug(traceback.format_exc())
            finished_by_type[entity_type] = finished_by_type.get(entity_type, 0) + 1
            if progress_callback is not None:
                progress_callback(
                    entity_type,
                    finished_by_type.get(entity_type, completed_count),
                    max(totals_by_type.get(entity_type, total_tasks), 1),
                    progress_message,
                )

    end_time = time.time()
    logger.success(f"映射完成: {' 和 '.join(summary_parts)}，耗时 {end_time - start_time:.2f}s")


def build_mapping_all(  # noqa: PLR0913
    reader: DataReader,
    max_workers: int = 4,
    include_champions: bool = True,
    include_maps: bool = True,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """使用线程池并发构建所有实体的事件映射

    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :param max_workers: 使用的最大线程数 (1: 单线程, >1: 多线程)
    :param include_champions: 是否包含英雄映射
    :param include_maps: 是否包含地图映射
    :param integrate_data: 是否生成整合数据
    """
    tasks = []

    # 生成英雄任务
    if include_champions:
        champion_tasks = generate_champion_tasks(reader, None)
        tasks.extend(champion_tasks)
        logger.debug(f"已添加 {len(champion_tasks)} 个英雄映射任务")

    # 生成地图任务
    if include_maps:
        map_tasks = generate_map_tasks(reader, None)
        tasks.extend(map_tasks)
        logger.debug(f"已添加 {len(map_tasks)} 个地图映射任务")

    if not tasks:
        logger.warning("没有找到任何需要映射的实体")
        return

    # 执行任务
    execute_mapping_tasks(
        tasks,
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )


def build_champions_mapping(  # noqa: PLR0913
    reader: DataReader,
    champion_ids: list[int],
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """便捷函数：构建指定英雄的事件映射

    :param reader: 数据读取器
    :param champion_ids: 英雄ID列表
    :param max_workers: 最大工作线程数
    :param integrate_data: 是否生成整合数据
    :raises ValueError: 当指定的ID不存在时
    """
    tasks = generate_champion_tasks(reader, champion_ids)
    execute_mapping_tasks(
        tasks,
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )


def build_maps_mapping(  # noqa: PLR0913
    reader: DataReader,
    map_ids: list[int],
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> None:
    """便捷函数：构建指定地图的事件映射

    :param reader: 数据读取器
    :param map_ids: 地图ID列表
    :param max_workers: 最大工作线程数
    :param integrate_data: 是否生成整合数据
    :raises ValueError: 当指定的ID不存在时
    """
    tasks = generate_map_tasks(reader, map_ids)
    execute_mapping_tasks(
        tasks,
        reader,
        max_workers,
        integrate_data,
        ctx=ctx,
        progress_callback=progress_callback,
    )


def main():
    """示例：构建单个英雄的事件映射"""
    from lol_audio_unpack import setup_app  # noqa: PLC0415

    ctx = setup_app(dev_mode=True, log_level="INFO")
    logger.disable("league_tools")

    reader = DataReader(ctx=ctx)
    # 示例：构建安妮(ID=1)的事件映射
    result = build_champion_mapping(1, reader, ctx=ctx)
    logger.info(f"映射结果: {len(result.get('skins', {}))} 个皮肤")


if __name__ == "__main__":
    main()
