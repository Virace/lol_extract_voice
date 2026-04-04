"""单实体解包与输出路径逻辑。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.utils.logging import performance_monitor
from lol_audio_unpack.utils.path_constants import (
    format_entity_folder_name,
    format_sub_entity_folder_name,
    get_output_dir_name,
)
from lol_audio_unpack.utils.stats import FileProcessResult, ProcessingStatsContext

from .bp_vo import attach_bp_vo

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext

AUDIO_TYPE_VO = "VO"


def _persist_wem(
    file: Any,
    destination_path: Path,
    *,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_submitter: Callable[[Path], None] | None = None,
) -> None:
    """保存 ``.wem`` 文件，并在成功后通知 WAV sidecar。

    Args:
        file: 具备 ``save_file`` 方法的提取结果对象。
        destination_path: 落盘目标路径。
        persisted_wem_callback: 文件成功落盘后的附加回调。
        wav_submitter: 可选的 WAV sidecar 提交回调。
    """
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    file.save_file(destination_path)
    if persisted_wem_callback is not None:
        persisted_wem_callback(destination_path)
    if wav_submitter is not None:
        wav_submitter(destination_path)


def _get_region(ctx: AppContext) -> str:
    """获取当前运行语言区域。"""
    return str(ctx.config.game_region or "zh_CN")


def _get_audio_root(ctx: AppContext) -> Path:
    """获取音频输出根目录。"""
    return Path(ctx.paths.audio_path)


def _get_report_root(ctx: AppContext) -> Path:
    """获取报告输出根目录。"""
    return Path(ctx.paths.report_path)


def _get_includes(ctx: AppContext) -> list[str]:
    """获取包含的音频类型列表。"""
    return list(ctx.config.include_types)


def _get_excludes(ctx: AppContext) -> list[str]:
    """获取排除的音频类型列表。"""
    return list(ctx.config.exclude_types)


def _is_group_by_type(ctx: AppContext) -> bool:
    """是否按音频类型优先分组输出。"""
    return bool(ctx.config.group_by_type)


def _get_vo_type(_ctx: AppContext) -> str:
    """获取 VO 音频类型常量。"""
    return AUDIO_TYPE_VO


def _get_wad_instance(
    wad_path: Path,
    wad_cache: dict[Path, WAD] | None,
    cache_lock: threading.Lock | None,
) -> WAD:
    """获取 WAD 实例并复用缓存。

    Args:
        wad_path: WAD 文件绝对路径。
        wad_cache: 本轮解包共享缓存；为 ``None`` 时不缓存。
        cache_lock: 多线程场景下的缓存锁。

    Returns:
        对应路径的 ``WAD`` 实例。
    """
    if wad_cache is None:
        return WAD(wad_path)

    if cache_lock is None:
        if wad_path not in wad_cache:
            wad_cache[wad_path] = WAD(wad_path)
        return wad_cache[wad_path]

    with cache_lock:
        if wad_path not in wad_cache:
            wad_cache[wad_path] = WAD(wad_path)
        return wad_cache[wad_path]


@logger.catch
@performance_monitor(level="DEBUG")
def unpack_entity(  # noqa: PLR0913
    entity_data: AudioEntityData,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_submitter: Callable[[Path], None] | None = None,
) -> None:
    """解包单个实体音频。

    Args:
        entity_data: 实体数据。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_submitter: WAV sidecar 提交回调。

    Raises:
        ValueError: 实体数据无效时抛出。
    """
    language = _get_region(ctx)
    audio_path = _get_audio_root(ctx) / reader.version
    if not audio_path.exists():
        audio_path.mkdir(parents=True, exist_ok=True)

    include_types = _get_includes(ctx)
    exclude_types = _get_excludes(ctx)

    stats_context = ProcessingStatsContext(
        entity_data,
        reader.version,
        language,
        include_types,
        exclude_types,
    )
    with stats_context as stats:
        logger.info(f"解包 {entity_data.entity_name} (ID:{entity_data.entity_id})")
        logger.debug("阶段 1: 收集所有需要解包的音频文件路径...")

        vo_paths_to_extract = set()
        vo_path_to_sub_info_map: dict[str, dict[str, Any]] = {}
        other_paths_to_extract = set()
        other_path_to_sub_info_map: dict[str, dict[str, Any]] = {}

        stats.total_sub_entities = len(entity_data.sub_entities)

        for sub_id, sub_data in entity_data.sub_entities.items():
            sub_info = entity_data.get_sub_entity_info(sub_id)
            if not sub_info:
                logger.warning(f"子实体ID {sub_id} 信息不完整，跳过处理")
                stats.record_sub_entity_skipped(sub_id, "信息不完整")
                continue

            stats.processed_sub_entities += 1
            sub_name = sub_info["name"]
            sub_id_int = sub_info["id"]

            for category, banks_list in sub_data["categories"].items():
                audio_type = reader.get_audio_type(category)
                if audio_type in exclude_types:
                    continue

                sub_info_with_type = {
                    "id": sub_id_int,
                    "name": sub_name,
                    "type": audio_type,
                }

                if audio_type == _get_vo_type(ctx):
                    for bank in banks_list:
                        for path in bank:
                            vo_paths_to_extract.add(path)
                            vo_path_to_sub_info_map[path] = sub_info_with_type
                else:
                    for bank in banks_list:
                        for path in bank:
                            other_paths_to_extract.add(path)
                            other_path_to_sub_info_map[path] = sub_info_with_type

        stats.vo_paths_count = len(vo_paths_to_extract)
        stats.sfx_music_paths_count = len(other_paths_to_extract)

        if not vo_paths_to_extract and not other_paths_to_extract:
            logger.warning(
                f"{entity_data.entity_type} '{entity_data.entity_name}' 未找到任何需要解包的音频文件 (检查排除类型配置)。"
            )
            return

        logger.debug("阶段 2: 开始批量解包WAD文件...")
        path_to_raw_data_map: dict[str, bytes] = {}

        lang_wad_path = entity_data.get_wad_path("VO", ctx=ctx)
        if lang_wad_path and vo_paths_to_extract:
            vo_path_list = list(vo_paths_to_extract)
            try:
                logger.debug(f"正在从 {lang_wad_path.name} 解包 {len(vo_path_list)} 个VO文件...")
                wad_obj = _get_wad_instance(lang_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(vo_path_list, raw=True)
                path_to_raw_data_map.update(zip(vo_path_list, file_raws, strict=False))
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), len(file_raws))
            except Exception as e:
                logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).error(
                    f"解包语言WAD文件 '{lang_wad_path.name}' 时出错: {e}"
                )
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), 0, str(e))
        elif vo_paths_to_extract:
            logger.warning("语言WAD文件不存在，跳过VO解包。")
            stats.set_wad_info("VO", None, len(vo_paths_to_extract), 0, "WAD文件不存在")

        root_wad_path = entity_data.get_wad_path("SFX", ctx=ctx)
        if root_wad_path and other_paths_to_extract:
            other_path_list = list(other_paths_to_extract)
            try:
                logger.debug(f"正在从 {root_wad_path.name} 解包 {len(other_path_list)} 个SFX/Music文件...")
                wad_obj = _get_wad_instance(root_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(other_path_list, raw=True)
                path_to_raw_data_map.update(zip(other_path_list, file_raws, strict=False))
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), len(file_raws))
            except Exception as e:
                logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).error(
                    f"解包根WAD文件 '{root_wad_path.name}' 时出错: {e}"
                )
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), 0, str(e))
        elif other_paths_to_extract:
            logger.warning("根WAD文件不存在，跳过SFX/Music解包。")
            stats.set_wad_info("ROOT", None, len(other_paths_to_extract), 0, "WAD文件不存在")

        logger.debug("阶段 3: 组装并处理最终数据...")
        path_to_sub_info_map = {**vo_path_to_sub_info_map, **other_path_to_sub_info_map}
        unpacked_audio_data: dict[int, dict[str, Any]] = {}

        for path, raw_data in path_to_raw_data_map.items():
            sub_info = path_to_sub_info_map.get(path)
            if not sub_info:
                continue

            sub_id = sub_info["id"]
            if sub_id not in unpacked_audio_data:
                unpacked_audio_data[sub_id] = {"name": sub_info["name"], "files": []}

            unpacked_audio_data[sub_id]["files"].append(
                {
                    "suffix": Path(path).suffix,
                    "raw": raw_data,
                    "type": sub_info["type"],
                    "source_path": path,
                }
            )

        total_assembled_files = sum(len(sub_data["files"]) for sub_data in unpacked_audio_data.values())
        stats.record_assembly_stats(len(unpacked_audio_data), total_assembled_files)
        logger.debug(f"音频文件解包完成，共 {len(unpacked_audio_data)} 个子实体")

        for sub_id, sub_data in unpacked_audio_data.items():
            sub_name = sub_data["name"]
            files = sub_data["files"]
            sub_id_str = str(sub_id)

            files_by_type: dict[str, list[dict[str, Any]]] = {}
            for file_info in files:
                audio_type = file_info["type"]
                if audio_type not in files_by_type:
                    files_by_type[audio_type] = []
                files_by_type[audio_type].append(file_info)

            for audio_type, files_in_type in files_by_type.items():
                output_path = generate_output_path(entity_data, sub_id_str, audio_type, audio_path, ctx=ctx)
                output_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"处理 {sub_name} ({audio_type}) - {len(files_in_type)} 个文件")

                for file_info in files_in_type:
                    file_size = len(file_info["raw"]) if file_info["raw"] else 0
                    source_path = file_info.get("source_path", "未知路径")
                    logger.trace(f"  - 类型: {file_info['suffix']}, 大小: {file_size} 字节")

                    if file_size == 0:
                        stats.record_file_result(
                            sub_id,
                            sub_name,
                            audio_type,
                            FileProcessResult.EMPTY_CONTAINER,
                            source_path=source_path,
                        )
                        continue

                    if file_info["suffix"] == ".bnk":
                        try:
                            bnk = BNK(file_info["raw"])
                            for file in bnk.extract_files():
                                if not file.data:
                                    logger.warning(f"BNK, 文件 {file.id} 没有数据，跳过保存")
                                    stats.record_file_result(
                                        sub_id,
                                        sub_name,
                                        audio_type,
                                        FileProcessResult.EMPTY_SUBFILE,
                                    )
                                    continue

                                _persist_wem(
                                    file,
                                    output_path / f"{file.id}.wem",
                                    persisted_wem_callback=persisted_wem_callback,
                                    wav_submitter=wav_submitter,
                                )
                                stats.record_file_result(sub_id, sub_name, audio_type, FileProcessResult.SUCCESS)
                        except Exception as e:
                            logger.warning(f"处理BNK文件失败: {e} | 文件路径: {source_path}")
                            stats.record_file_result(
                                sub_id,
                                sub_name,
                                audio_type,
                                FileProcessResult.PARSE_ERROR,
                                error_info={"path": source_path, "error": str(e), "type": "BNK"},
                            )
                    elif file_info["suffix"] == ".wpk":
                        try:
                            wpk = WPK(file_info["raw"])
                            for file in wpk.extract_files():
                                _persist_wem(
                                    file,
                                    output_path / f"{file.filename}",
                                    persisted_wem_callback=persisted_wem_callback,
                                    wav_submitter=wav_submitter,
                                )
                                stats.record_file_result(sub_id, sub_name, audio_type, FileProcessResult.SUCCESS)
                        except Exception as e:
                            logger.warning(f"处理WPK文件失败: {e} | 文件路径: {source_path}")
                            stats.record_file_result(
                                sub_id,
                                sub_name,
                                audio_type,
                                FileProcessResult.PARSE_ERROR,
                                error_info={"path": source_path, "error": str(e), "type": "WPK"},
                            )
                    else:
                        logger.warning(f"未知的文件类型: {file_info['suffix']} | 文件路径: {source_path}")
                        stats.record_file_result(
                            sub_id,
                            sub_name,
                            audio_type,
                            FileProcessResult.UNKNOWN_TYPE,
                            error_info={
                                "path": source_path,
                                "error": f"未知文件类型: {file_info['suffix']}",
                                "type": "UNKNOWN",
                            },
                        )

    summary = stats.get_simple_summary()

    if stats.overall_result.value == "success":
        logger.success(summary)
    elif stats.overall_result.value == "warning":
        logger.warning(summary)
    else:
        logger.error(summary)

    if stats.overall_result.value != "success":
        for sub_stats in stats.sub_entity_stats.values():
            if sub_stats.failed_file_details:
                logger.debug(f"{sub_stats.name} 失败文件详情:")
                for failed_file in sub_stats.failed_file_details:
                    logger.debug(
                        f"  - 类型: {failed_file.get('type', 'UNKNOWN')}, "
                        f"错误: {failed_file.get('error', 'Unknown error')}, "
                        f"路径: {failed_file.get('path', 'Unknown path')}"
                    )

            if sub_stats.empty_container_paths:
                logger.debug(f"{sub_stats.name} 空容器路径: {sub_stats.empty_container_paths}")

    try:
        report_filename = f"_{entity_data.entity_id}_metadata.yaml"
        report_path = (
            _get_report_root(ctx) / reader.version / get_output_dir_name(entity_data.entity_type) / report_filename
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        stats.save_concise_report_to_yaml(report_path)
    except Exception as e:
        logger.debug(f"保存报告文件失败: {e}")


def _generate_relative_path(entity_data: AudioEntityData, sub_id: str) -> Path:
    """生成不含音频类型的相对目录。

    Args:
        entity_data: 实体数据。
        sub_id: 子实体 ID。

    Returns:
        相对于音频根目录的实体路径。
    """
    sub_name = entity_data.sub_entities[sub_id]["name"]
    entity_dir = get_output_dir_name(entity_data.entity_type)
    entity_folder = format_entity_folder_name(
        entity_data.entity_id,
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )

    if entity_data.entity_type == "champion":
        sub_folder = format_sub_entity_folder_name(sub_id, sub_name)
        return Path(entity_dir) / entity_folder / sub_folder

    return Path(entity_dir) / entity_folder


def generate_output_path(
    entity_data: AudioEntityData,
    sub_id: str,
    audio_type: str,
    base_path: Path | None = None,
    *,
    ctx: AppContext,
) -> Path:
    """生成音频输出目录。

    Args:
        entity_data: 实体数据。
        sub_id: 子实体 ID。
        audio_type: 音频类型。
        base_path: 输出根目录；为空时使用 ``ctx.paths.audio_path``。
        ctx: 运行时上下文。

    Returns:
        对应音频类型的目标目录路径。
    """
    if base_path is None:
        base_path = _get_audio_root(ctx)

    relative_path = _generate_relative_path(entity_data, sub_id)
    if _is_group_by_type(ctx):
        return base_path / audio_type / relative_path
    return base_path / relative_path / audio_type


def unpack_champion(  # noqa: PLR0913
    champion_id: int,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_submitter: Callable[[Path], None] | None = None,
) -> None:
    """按英雄 ID 解包音频。

    Args:
        champion_id: 英雄 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_submitter: WAV sidecar 提交回调。
    """
    try:
        entity_data = AudioEntityData.from_champion(champion_id, reader, ctx=ctx)
        unpack_entity(
            entity_data,
            reader,
            wad_cache=wad_cache,
            cache_lock=cache_lock,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
            wav_submitter=wav_submitter,
        )
        attach_bp_vo(entity_data, reader, ctx=ctx)
    except ValueError as e:
        logger.error(str(e))
        return


def unpack_map(  # noqa: PLR0913
    map_id: int,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
    wav_submitter: Callable[[Path], None] | None = None,
) -> None:
    """按地图 ID 解包音频。

    Args:
        map_id: 地图 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。
        wav_submitter: WAV sidecar 提交回调。
    """
    try:
        entity_data = AudioEntityData.from_map(map_id, reader, ctx=ctx)
        unpack_entity(
            entity_data,
            reader,
            wad_cache=wad_cache,
            cache_lock=cache_lock,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
            wav_submitter=wav_submitter,
        )
    except ValueError as e:
        logger.error(str(e))
        return


# 兼容层：等全项目统一收口后再移除旧名。
_persist_wem_and_maybe_submit = _persist_wem
unpack_audio_entity = unpack_entity
unpack_map_audio = unpack_map
