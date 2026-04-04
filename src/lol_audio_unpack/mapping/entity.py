"""单实体事件映射与整合流程。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools import AudioEventMapper, WwiserManager
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.utils import create_metadata_object, write_data
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.utils.logging import performance_monitor

from . import session as mapping_session

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


def _ensure_version_dirs(reader: DataReader, *, ctx: AppContext) -> tuple[Path, Path]:
    """创建并返回版本化的 cache/hash 目录。

    Args:
        reader: 数据读取器实例。
        ctx: 运行时上下文。

    Returns:
        tuple[Path, Path]: ``(version_cache_dir, version_hash_dir)``。
    """

    version_cache_dir = ctx.cache_path / reader.version
    version_hash_dir = ctx.hash_path / reader.version
    version_cache_dir.mkdir(parents=True, exist_ok=True)
    version_hash_dir.mkdir(parents=True, exist_ok=True)
    return version_cache_dir, version_hash_dir


def _build_mapping_result(entity_data: AudioEntityData, reader: DataReader) -> tuple[dict[str, Any], str]:
    """创建映射结果骨架。

    Args:
        entity_data: 当前实体数据。
        reader: 数据读取器实例。

    Returns:
        tuple[dict[str, Any], str]: 映射结果骨架与数据键名。

    Raises:
        ValueError: 实体类型未知时抛出。
    """

    base_data = create_metadata_object(reader.version, reader.get_languages())
    if entity_data.entity_type == "champion":
        base_data["championId"] = entity_data.entity_id
        base_data["alias"] = entity_data.entity_alias
        base_data["skins"] = {}
        return base_data, "skins"
    if entity_data.entity_type == "map":
        base_data["mapId"] = entity_data.entity_id
        base_data["name"] = entity_data.entity_alias
        base_data["map"] = {}
        return base_data, "map"
    raise ValueError(f"未知的实体类型: {entity_data.entity_type}")


def _resolve_wad_path(entity_data: AudioEntityData, category: str, *, ctx: AppContext) -> Path | None:
    """根据类别选择当前应使用的 WAD 文件。

    Args:
        entity_data: 当前实体数据。
        category: 音频类别名称。
        ctx: 运行时上下文。

    Returns:
        Path | None: 可用的 WAD 文件路径；不可用时返回 ``None``。
    """

    # WAD 选择规则统一收口到 AudioEntityData；
    # mapping 层只负责把“类别名”翻译成模型认识的音频类型。
    audio_type = "VO" if "VO" in category else "SFX"
    wad_path = entity_data.get_wad_path(audio_type, ctx=ctx)
    if wad_path is not None:
        return wad_path

    # 这里保留 mapping 侧原有的日志语义：
    # VO 缺语言包和“路径声明存在但文件缺失”都要继续可见，而不是重构后静默失败。
    if audio_type == "VO" and not entity_data.wad_language:
        logger.warning(f"VO类别但无语言WAD文件: {category}")
        return None

    relative_path = entity_data.wad_language if audio_type == "VO" else entity_data.wad_root
    if relative_path:
        logger.warning(f"WAD文件不存在: {ctx.game_path / relative_path}")
    return None


def _build_category_mapping(  # noqa: PLR0913
    entity_data: AudioEntityData,
    category: str,
    paths_list: list[list[str]],
    event_list: list[str],
    version_cache_dir: Path,
    wwiser_manager: WwiserManager | None,
    runtime_cache: mapping_session.RuntimeCache | None,
    *,
    ctx: AppContext,
) -> tuple[Any | None, int]:
    """构建单个类别的映射结果。

    Args:
        entity_data: 当前实体数据。
        category: 当前类别名称。
        paths_list: 当前类别的路径组合列表。
        event_list: 当前类别的事件列表。
        version_cache_dir: 版本化 cache 目录。
        wwiser_manager: 可选的 wwiser 管理器。
        runtime_cache: 映射流程共享缓存。
        ctx: 运行时上下文。

    Returns:
        tuple[Any | None, int]: 合并后的映射对象与异常路径组数量。
    """

    if len(paths_list) > 1:
        logger.info(f"特殊情况，{entity_data.entity_id} {category} 有 {len(paths_list)} 个路径组合，将逐个处理并合并")

    category_mapping = None
    category_error_count = 0
    hirc_cache_dir = version_cache_dir / "hirc"
    hirc_cache_dir.mkdir(parents=True, exist_ok=True)

    for path_group_idx, path_group in enumerate(paths_list):
        logger.debug(f"处理路径组合 {path_group_idx + 1}/{len(paths_list)}: {path_group}")

        bnk_paths = [path for path in path_group if path.endswith("_events.bnk")]
        if len(bnk_paths) != 1:
            if len(bnk_paths) == 0:
                logger.debug(f"路径组合 {path_group_idx + 1} 无 events.bnk 文件，跳过")
            else:
                logger.warning(f"路径组合 {path_group_idx + 1} 的 events.bnk 文件数量异常: {len(bnk_paths)}")
            continue

        wad_path = _resolve_wad_path(entity_data, category, ctx=ctx)
        if wad_path is None:
            continue

        try:
            wad_obj = mapping_session._get_wad(wad_path, runtime_cache=runtime_cache)
            bnk_rel_path = bnk_paths[0]
            extract_key = (wad_path, bnk_rel_path)
            if not mapping_session._is_bnk_extracted(extract_key, runtime_cache=runtime_cache):
                wad_obj.extract(bnk_paths, out_dir=version_cache_dir)
                mapping_session._mark_bnk_extracted(extract_key, runtime_cache=runtime_cache)

            bnk_path = version_cache_dir / bnk_rel_path
            if not bnk_path.exists():
                logger.warning(f"提取的BNK文件不存在: {bnk_path}")
                continue

            hirc = mapping_session._get_cached_hirc(
                bnk_path=bnk_path,
                hirc_cache_dir=hirc_cache_dir,
                wwiser_manager=wwiser_manager,
                runtime_cache=runtime_cache,
            )
            current_mapping = AudioEventMapper(event_list, hirc).build_mapping()

            if category_mapping is None:
                category_mapping = current_mapping
                logger.debug(f"路径组合 {path_group_idx + 1}: 创建基础映射，事件数: {len(event_list)}")
                continue

            category_mapping.merge_with(current_mapping)
            logger.debug(f"路径组合 {path_group_idx + 1}: 合并映射完成")
        except Exception as exc:  # noqa: BLE001
            category_error_count += 1
            logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).warning(
                f"处理路径组合 {path_group_idx + 1} 时出错: {exc}"
            )

    return category_mapping, category_error_count


def _write_integrated_result(
    entity_data: AudioEntityData,
    integrated_result: dict[str, Any],
    version_hash_dir: Path,
    *,
    ctx: AppContext,
) -> None:
    """保存整合结果到文件。

    Args:
        entity_data: 当前实体数据。
        integrated_result: 已整合的完整输出。
        version_hash_dir: 版本化 hash 目录。
        ctx: 运行时上下文。
    """

    data_key = "skins" if entity_data.entity_type == "champion" else "map"
    if not integrated_result or not integrated_result.get("data", {}).get(data_key):
        return

    entity_group = "champions" if entity_data.entity_type == "champion" else "maps"
    integration_save_dir = version_hash_dir / "integrated" / entity_group
    integration_save_dir.mkdir(parents=True, exist_ok=True)
    integration_file_base = integration_save_dir / entity_data.entity_id
    write_data(integrated_result, integration_file_base, dev_mode=ctx.config.dev_mode)
    logger.debug(f"整合数据已保存: {integration_file_base}")


def _write_mapping_result(
    mapping_result: dict[str, Any],
    mapping_data_key: str,
    mapping_save_dir: Path,
    entity_data: AudioEntityData,
    *,
    ctx: AppContext,
) -> None:
    """保存纯 mapping 结果到文件。

    Args:
        mapping_result: 当前映射结果。
        mapping_data_key: 当前实体使用的数据键。
        mapping_save_dir: 目标输出目录。
        entity_data: 当前实体数据。
        ctx: 运行时上下文。
    """

    metadata = mapping_result.get("metadata", {})
    if "languages" in metadata:
        del metadata["languages"]

    if mapping_result[mapping_data_key]:
        mapping_file_base = mapping_save_dir / entity_data.entity_id
        write_data(mapping_result, mapping_file_base, dev_mode=ctx.config.dev_mode)
        logger.debug(f"映射结果已保存: {mapping_file_base}")
        return

    logger.warning(f"{entity_data.entity_name} 没有找到任何有效映射数据")


def _log_entity_summary(
    entity_name: str,
    *,
    mapped_count: int,
    errored_count: int,
    skipped_count: int,
    integrate_data: bool,
) -> None:
    """输出实体级摘要日志。

    Args:
        entity_name: 实体名称。
        mapped_count: 成功映射事件数。
        errored_count: 异常事件数。
        skipped_count: 未映射跳过事件数。
        integrate_data: 当前是否为整合模式。
    """

    summary_prefix = "整合数据统计" if integrate_data else "事件映射统计"
    summary_message = (
        f"{entity_name} 的{summary_prefix}：成功映射事件 {mapped_count} 个，"
        f"异常事件 {errored_count} 个，未映射跳过 {skipped_count} 个"
    )
    if errored_count > 0:
        if mapped_count > 0 or skipped_count > 0:
            logger.warning(summary_message)
        else:
            logger.error(summary_message)
        return
    logger.success(summary_message)


@logger.catch
@performance_monitor(level="DEBUG")
def build_entity(  # noqa: PLR0913
    entity_data: AudioEntityData,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: mapping_session.RuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个实体的事件映射。

    Args:
        entity_data: 包含 events 的实体数据。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器；为 ``None`` 时按 ``ctx`` 自动选择后端。
        integrate_data: 是否输出整合数据。
        runtime_cache: 映射流程共享缓存，用于复用 WAD/HIRC 解析结果。
        ctx: 运行时上下文。

    Returns:
        dict[str, Any]: 映射结果或整合结果。

    Raises:
        ValueError: 实体没有可用 events 数据时抛出。
    """

    if not entity_data.events:
        raise ValueError(f"{entity_data.entity_name} 缺少事件数据，请使用 include_events=True 创建实体数据")

    logger.info(f"构建 {entity_data.entity_name} (ID:{entity_data.entity_id}) 的事件映射")
    manager = mapping_session._create_wwiser_manager(ctx) if wwiser_manager is None else wwiser_manager
    version_cache_dir, version_hash_dir = _ensure_version_dirs(reader, ctx=ctx)
    mapping_result, mapping_data_key = _build_mapping_result(entity_data, reader)
    entity_group = "champions" if entity_data.entity_type == "champion" else "maps"
    mapping_save_dir = version_hash_dir / entity_group
    mapping_save_dir.mkdir(parents=True, exist_ok=True)

    mapped_event_count = 0
    errored_event_count = 0
    skipped_event_count = 0

    for sub_id, sub_data in entity_data.sub_entities.items():
        banks_data = sub_data["categories"]
        events_data = entity_data.events.get(sub_id, {}).get("events", {})
        if not events_data:
            logger.debug(f"子实体 {sub_id} 无事件数据，跳过")
            continue

        sub_mapping: dict[str, dict[str, list[int]]] = {}
        for category, paths_list in banks_data.items():
            event_list = events_data.get(category, [])
            if not event_list:
                logger.debug(f"类别 {category} 无事件列表，跳过")
                continue

            logger.debug(f"处理类别: {category}")
            category_mapping, category_error_count = _build_category_mapping(
                entity_data,
                category,
                paths_list,
                event_list,
                version_cache_dir,
                manager,
                runtime_cache,
                ctx=ctx,
            )

            if category_mapping is not None and category_mapping.forward_mapping:
                mapped_count = len(category_mapping.forward_mapping)
                skipped_count = max(len(event_list) - mapped_count, 0)
                mapped_event_count += mapped_count
                skipped_event_count += skipped_count
                sub_mapping[category] = category_mapping.forward_mapping
                logger.debug(
                    f"完成 {category} 的映射，处理了 {len(paths_list)} 个路径组合，事件数: {len(event_list)}，"
                    f"映射条目: {mapped_count}，未映射跳过: {skipped_count}"
                )
                continue

            if category_mapping is not None:
                skipped_event_count += len(event_list)
                logger.warning(f"类别 {category} 映射结果为空，跳过保存")
                continue

            if category_error_count > 0:
                errored_event_count += len(event_list)
            else:
                skipped_event_count += len(event_list)
            logger.warning(f"类别 {category} 没有生成任何有效的映射结果")

        if sub_mapping:
            mapping_result[mapping_data_key][sub_id] = {"events": sub_mapping}
            logger.debug(f"子实体 {sub_id} 保存了 {len(sub_mapping)} 个有效类别的映射")
        else:
            logger.debug(f"子实体 {sub_id} 无有效映射数据，跳过保存")

    if integrate_data:
        integrated_result = integrate_entity(entity_data, reader, mapping_result)
        _write_integrated_result(entity_data, integrated_result, version_hash_dir, ctx=ctx)
        _log_entity_summary(
            entity_data.entity_name,
            mapped_count=mapped_event_count,
            errored_count=errored_event_count,
            skipped_count=skipped_event_count,
            integrate_data=True,
        )
        return integrated_result

    _write_mapping_result(mapping_result, mapping_data_key, mapping_save_dir, entity_data, ctx=ctx)
    _log_entity_summary(
        entity_data.entity_name,
        mapped_count=mapped_event_count,
        errored_count=errored_event_count,
        skipped_count=skipped_event_count,
        integrate_data=False,
    )
    return mapping_result


def integrate_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    mapping_result: dict[str, Any],
) -> dict[str, Any]:
    """整合实体数据，将 banks、events 与 mapping 合并为完整结构。

    Args:
        entity_data: 音频实体数据。
        reader: 数据读取器实例。
        mapping_result: 当前实体的映射结果。

    Returns:
        dict[str, Any]: 整合后的完整实体数据。
    """

    logger.info(f"开始整合 {entity_data.entity_name} 的数据")

    if entity_data.entity_type == "champion":
        entity_info = reader.get_champion(int(entity_data.entity_id))
        banks_data = reader.get_champion_banks(int(entity_data.entity_id))
        data_key = "skins"
    else:
        entity_info = reader.get_map(int(entity_data.entity_id))
        banks_data = reader.get_map_banks(int(entity_data.entity_id))
        data_key = "map"

    if not entity_info or not banks_data:
        logger.warning(f"无法获取 {entity_data.entity_name} 的完整数据信息")
        return {}

    integrated_data = {"metadata": mapping_result.get("metadata", {}), "data": {}}
    wad_info = {"root": entity_data.wad_root}
    if entity_data.wad_language:
        wad_info["language"] = entity_data.wad_language

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
        sub_entities = entity_info.get("skins", [])
    else:
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
        sub_entities = [{"id": int(entity_data.entity_id)}]

    mapping_data = mapping_result.get(data_key, {})
    processed_items = []

    for sub_entity in sub_entities:
        sub_id = str(sub_entity["id"])
        if sub_id not in mapping_data:
            logger.debug(f"皮肤/地图 {sub_id} 没有事件数据，跳过")
            continue

        integrated_item = {"id": sub_entity["id"]}
        if entity_data.entity_type == "champion":
            integrated_item.update(
                {
                    "isBase": sub_entity.get("isBase", False),
                    "skinNames": sub_entity.get("skinNames", {}),
                    "binPath": sub_entity.get("binPath", ""),
                }
            )
        integrated_item["events"] = {}

        sub_banks = (
            banks_data.get("skins", {}).get(sub_id, {})
            if entity_data.entity_type == "champion"
            else banks_data.get("banks", {})
        )
        sub_mapping = mapping_data.get(sub_id, {}).get("events", {})

        for category in sub_mapping.keys():
            banks_paths = sub_banks.get(category, [])
            mapping_events = sub_mapping.get(category, {})
            if banks_paths and mapping_events:
                integrated_item["events"][category] = {"banks": banks_paths, "mapping": mapping_events}

        if integrated_item["events"]:
            processed_items.append(integrated_item)
            logger.debug(f"皮肤/地图 {sub_id} 整合完成，包含 {len(integrated_item['events'])} 个音频类别")

    if entity_data.entity_type == "champion":
        integrated_data["data"]["skins"] = processed_items
    elif processed_items:
        integrated_data["data"]["map"] = processed_items[0]

    logger.success(f"整合完成，{entity_data.entity_name} 包含 {len(processed_items)} 个有效皮肤/地图数据")
    return integrated_data


def build_champion(  # noqa: PLR0913
    champion_id: int,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: mapping_session.RuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个英雄的事件映射。

    Args:
        champion_id: 英雄 ID。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器。
        integrate_data: 是否输出整合数据。
        runtime_cache: 映射流程共享缓存。
        ctx: 运行时上下文。

    Returns:
        dict[str, Any]: 英雄映射结果；失败时返回空字典。
    """

    try:
        entity_data = AudioEntityData.from_champion(champion_id, reader, include_events=True, ctx=ctx)
        return build_entity(
            entity_data,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
    except ValueError as exc:
        logger.error(str(exc))
        return {}


def build_map(  # noqa: PLR0913
    map_id: int,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: mapping_session.RuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]:
    """构建单个地图的事件映射。

    Args:
        map_id: 地图 ID。
        reader: 数据读取器实例。
        wwiser_manager: 可复用的 wwiser 管理器。
        integrate_data: 是否输出整合数据。
        runtime_cache: 映射流程共享缓存。
        ctx: 运行时上下文。

    Returns:
        dict[str, Any]: 地图映射结果；失败时返回空字典。
    """

    try:
        entity_data = AudioEntityData.from_map(map_id, reader, include_events=True, ctx=ctx)
        return build_entity(
            entity_data,
            reader,
            wwiser_manager,
            integrate_data,
            runtime_cache=runtime_cache,
            ctx=ctx,
        )
    except ValueError as exc:
        logger.error(str(exc))
        return {}
