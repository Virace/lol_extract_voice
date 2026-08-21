"""单实体解包与输出路径逻辑。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.app.path_layout import (
    format_entity_folder_name,
    format_sub_entity_folder_name,
    get_entity_path_component,
    get_output_dir_name,
)
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import AudioBank, AudioEntityData
from lol_audio_unpack.model.binding import SUCCESS_STATUSES
from lol_audio_unpack.runtime.wad import get_wad, resolve_bound_wad
from lol_audio_unpack.utils.logging import performance_monitor

from .bp_vo import attach_bp_vo
from .stats import EntityUnpackStats, FileProcessResult, ProcessingStatsContext

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

AUDIO_TYPE_VO = "VO"


def _persist_wem(
    file: Any,
    destination_path: Path,
    *,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> None:
    """保存 ``.wem`` 文件，并在成功后通知通用回调。

    Args:
        file: 具备 ``save_file`` 方法的提取结果对象。
        destination_path: 落盘目标路径。
        persisted_wem_callback: 文件成功落盘后的附加回调。
    """
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    file.save_file(destination_path)
    if persisted_wem_callback is not None:
        persisted_wem_callback(destination_path)


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
    # WAD 缓存语义已经收口到 runtime.wad；
    # unpack 侧继续保留这个薄入口，是为了不改动当前调用面和类型签名。
    return get_wad(wad_path, cache=wad_cache, lock=cache_lock)


def _record_bound_result(
    stats: EntityUnpackStats,
    bank: AudioBank,
    *,
    outcome: str,
    error: str | None = None,
) -> None:
    """把一个 binding 的消费结论写入实体级诊断。"""
    binding = bank.binding
    stats.record_binding_result(
        sub_id=bank.sub_id,
        audio_type=bank.audio_type,
        category=binding.category,
        path=binding.normalized_path,
        wad=binding.wad,
        entry_hash=binding.entry_hash,
        status=binding.status.value,
        outcome=outcome,
        error=error,
    )


def _persist_bound_container(  # noqa: PLR0913, PLR0917
    raw_data: bytes,
    bank: AudioBank,
    entity_data: AudioEntityData,
    audio_path: Path,
    stats: EntityUnpackStats,
    persisted_paths: set[Path],
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None,
) -> bool:
    """解析一个精确 binding 容器，并将 WEM 回挂到其逻辑子实体。"""
    sub_info = entity_data.get_sub_entity_info(bank.sub_id)
    if sub_info is None:
        _record_bound_result(stats, bank, outcome="failed", error="子实体信息不完整")
        return False

    sub_id = sub_info["id"]
    sub_name = sub_info["name"]
    output_path = generate_output_path(entity_data, bank.sub_id, bank.audio_type, audio_path, ctx=ctx)
    output_path.mkdir(parents=True, exist_ok=True)
    source_path = bank.binding.normalized_path

    if not raw_data:
        stats.record_file_result(
            sub_id,
            sub_name,
            bank.audio_type,
            FileProcessResult.EMPTY_CONTAINER,
            source_path=source_path,
        )
        _record_bound_result(stats, bank, outcome="failed", error="容器为空")
        return False

    try:
        if bank.binding.kind == "BNK":
            files = BNK(raw_data).extract_files()

            def get_name(file: Any) -> str:
                """返回 BNK 内 WEM 的原始 ID 文件名。"""
                return f"{file.id}.wem"

        elif bank.binding.kind == "WPK":
            files = WPK(raw_data).extract_files()

            def get_name(file: Any) -> str:
                """返回 WPK 内保留的 WEM 文件名。"""
                return file.filename

        else:
            stats.record_file_result(
                sub_id,
                sub_name,
                bank.audio_type,
                FileProcessResult.UNKNOWN_TYPE,
                error_info={"path": source_path, "error": f"未知文件类型: {bank.binding.kind}", "type": "UNKNOWN"},
            )
            _record_bound_result(stats, bank, outcome="failed", error=f"未知文件类型: {bank.binding.kind}")
            return False

        has_content = False
        for file in files:
            if not getattr(file, "data", True):
                stats.record_file_result(sub_id, sub_name, bank.audio_type, FileProcessResult.EMPTY_SUBFILE)
                continue

            has_content = True
            destination_path = output_path / get_name(file)
            if destination_path not in persisted_paths:
                _persist_wem(file, destination_path, persisted_wem_callback=persisted_wem_callback)
                persisted_paths.add(destination_path)
            stats.record_file_result(sub_id, sub_name, bank.audio_type, FileProcessResult.SUCCESS)

        if not has_content:
            _record_bound_result(stats, bank, outcome="failed", error="容器内没有可写入的 WEM")
            return False
    except Exception as exc:  # noqa: BLE001
        container_type = bank.binding.kind or Path(source_path).suffix.removeprefix(".").upper()
        logger.warning(f"处理{container_type}文件失败: {exc} | 文件路径: {source_path}")
        stats.record_file_result(
            sub_id,
            sub_name,
            bank.audio_type,
            FileProcessResult.PARSE_ERROR,
            error_info={"path": source_path, "error": str(exc), "type": container_type},
        )
        _record_bound_result(stats, bank, outcome="failed", error=str(exc))
        return False

    _record_bound_result(stats, bank, outcome="success")
    return True


def _unpack_bound_entity(  # noqa: PLR0913, PLR0917
    entity_data: AudioEntityData,
    audio_path: Path,
    exclude_types: list[str],
    stats: EntityUnpackStats,
    wad_cache: dict[Path, WAD] | None,
    cache_lock: threading.Lock | None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None,
) -> None:
    """仅按 local v2 成功 binding 的物理 WAD 与 entry 提取音频。"""
    stats.total_sub_entities = len(entity_data.sub_entities)
    requested: dict[str, dict[tuple[str, str], AudioBank]] = {}
    active_banks: list[AudioBank] = []

    for bank in entity_data.resource_banks:
        binding = bank.binding
        if bank.audio_type in exclude_types:
            continue
        if binding.status not in SUCCESS_STATUSES:
            _record_bound_result(stats, bank, outcome="unresolved", error=binding.diagnostic)
            continue
        if not binding.wad:
            _record_bound_result(stats, bank, outcome="failed", error="成功 binding 缺少 WAD identity")
            continue

        active_banks.append(bank)
        key = (binding.wad, binding.entry_hash)
        requested.setdefault(binding.wad, {}).setdefault(key, bank)

    stats.processed_sub_entities = len({bank.sub_id for bank in active_banks})
    stats.vo_paths_count = sum(bank.audio_type == AUDIO_TYPE_VO for bank in active_banks)
    stats.sfx_music_paths_count = len(active_banks) - stats.vo_paths_count
    raw_by_key: dict[tuple[str, str], bytes] = {}
    raw_errors: dict[tuple[str, str], str] = {}

    for wad_identity, unique_banks in requested.items():
        try:
            wad_path = resolve_bound_wad(ctx.game_path, wad_identity)
        except ValueError as exc:
            error = str(exc)
            keys = tuple(unique_banks)
            stats.record_binding_wad(wad_identity, requested=len(keys), extracted=0, error=error)
            raw_errors.update(dict.fromkeys(keys, error))
            logger.warning(error)
            continue
        keys = tuple(unique_banks)
        if not wad_path.is_file():
            error = "WAD文件不存在"
            stats.record_binding_wad(wad_identity, requested=len(keys), extracted=0, error=error)
            raw_errors.update(dict.fromkeys(keys, error))
            logger.warning(f"WAD文件不存在，跳过 {len(keys)} 个 binding: {wad_path}")
            continue

        try:
            wad_obj = _get_wad_instance(wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
            paths = [unique_banks[key].binding.path for key in keys]
            raws = wad_obj.extract(paths, raw=True)
            for key, raw in zip(keys, raws, strict=False):
                if raw is None:
                    raw_errors[key] = "WAD未返回目标 entry"
                else:
                    raw_by_key[key] = raw
            stats.record_binding_wad(
                wad_identity,
                requested=len(keys),
                extracted=sum(key in raw_by_key for key in keys),
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            raw_errors.update(dict.fromkeys(keys, error))
            stats.record_binding_wad(wad_identity, requested=len(keys), extracted=0, error=error)
            logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).warning(
                f"按 binding 解包 WAD '{wad_path.name}' 时出错: {exc}"
            )

    persisted_paths: set[Path] = set()
    for bank in active_banks:
        binding = bank.binding
        key = (binding.wad or "", binding.entry_hash)
        raw_data = raw_by_key.get(key)
        if raw_data is None:
            _record_bound_result(stats, bank, outcome="failed", error=raw_errors.get(key, "未提取到 WAD entry"))
            continue
        _persist_bound_container(
            raw_data,
            bank,
            entity_data,
            audio_path,
            stats,
            persisted_paths,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
        )

    stats.record_assembly_stats(len({bank.sub_id for bank in active_banks}), len(raw_by_key))
    diagnostics = entity_data.binding_diagnostics
    source_completeness = "partial" if diagnostics is not None and diagnostics.unresolved_bins else "complete"
    stats.set_binding_completeness(source_completeness)


def _finish_unpack_stats(
    entity_data: AudioEntityData, reader: DataReader, stats: EntityUnpackStats, *, ctx: AppContext
) -> None:
    """输出 binding 分支的实体摘要，并写入与旧格式兼容的报告。"""
    summary = stats.get_simple_summary()
    if stats.overall_result.value == "success":
        logger.success(summary)
    elif stats.overall_result.value == "warning":
        logger.warning(summary)
    else:
        logger.error(summary)

    try:
        component = get_entity_path_component(entity_data.entity_type, entity_data.entity_id)
        report_filename = f"_{component}_metadata.yaml"
        report_path = ctx.report_path / reader.version / get_output_dir_name(entity_data.entity_type) / report_filename
        report_path.parent.mkdir(parents=True, exist_ok=True)
        stats.save_concise_report_to_yaml(report_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"保存报告文件失败: {exc}")


@logger.catch(reraise=True)
@performance_monitor(level="DEBUG")
def unpack_entity(  # noqa: PLR0913
    entity_data: AudioEntityData,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> EntityUnpackStats:
    """解包单个实体音频。

    Args:
        entity_data: 实体数据。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。

    Returns:
        保持现有报告 schema 的实体解包统计。

    Raises:
        ValueError: 实体数据无效时抛出。
    """
    # 这里消费的是 AppContext 暴露的标准化派生值；
    # unpack 层不再自己补 region/path fallback，避免与其他子域再次分叉。
    language = ctx.game_region
    audio_path = ctx.audio_path / reader.version
    if not audio_path.exists():
        audio_path.mkdir(parents=True, exist_ok=True)

    include_types = list(ctx.include_types)
    exclude_types = list(ctx.exclude_types)

    stats_context = ProcessingStatsContext(
        entity_data,
        reader.version,
        language,
        include_types,
        exclude_types,
    )
    if entity_data.binding_diagnostics is not None:
        with stats_context as stats:
            logger.info(f"按 resource binding 解包 {entity_data.entity_name} (ID:{entity_data.entity_id})")
            _unpack_bound_entity(
                entity_data,
                audio_path,
                exclude_types,
                stats,
                wad_cache,
                cache_lock,
                ctx=ctx,
                persisted_wem_callback=persisted_wem_callback,
            )
        _finish_unpack_stats(entity_data, reader, stats, ctx=ctx)
        return stats

    with stats_context as stats:
        logger.info(f"解包 {entity_data.entity_name} (ID:{entity_data.entity_id})")
        logger.debug("阶段 1: 收集所有需要解包的音频文件路径...")

        vo_paths = set()
        vo_info_by_path: dict[str, dict[str, Any]] = {}
        other_paths = set()
        other_info_by_path: dict[str, dict[str, Any]] = {}

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

                audio_info = {
                    "id": sub_id_int,
                    "name": sub_name,
                    "type": audio_type,
                }

                # 先按 VO / 非 VO 拆分提取集合，后面才能分别命中语言 WAD 与根 WAD。
                if audio_type == AUDIO_TYPE_VO:
                    for bank in banks_list:
                        for path in bank:
                            vo_paths.add(path)
                            vo_info_by_path[path] = audio_info
                else:
                    for bank in banks_list:
                        for path in bank:
                            other_paths.add(path)
                            other_info_by_path[path] = audio_info

        stats.vo_paths_count = len(vo_paths)
        stats.sfx_music_paths_count = len(other_paths)

        if not vo_paths and not other_paths:
            logger.warning(
                f"{entity_data.entity_type} '{entity_data.entity_name}' 未找到任何需要解包的音频文件 (检查排除类型配置)。"
            )
            return stats

        logger.debug("阶段 2: 开始批量解包WAD文件...")
        raw_by_path: dict[str, bytes] = {}

        lang_wad_path = entity_data.get_wad_path("VO", ctx=ctx)
        if lang_wad_path and vo_paths:
            vo_path_list = list(vo_paths)
            try:
                logger.debug(f"正在从 {lang_wad_path.name} 解包 {len(vo_path_list)} 个VO文件...")
                wad_obj = _get_wad_instance(lang_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(vo_path_list, raw=True)
                raw_by_path.update(zip(vo_path_list, file_raws, strict=False))
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), len(file_raws))
            except Exception as e:
                logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).error(
                    f"解包语言WAD文件 '{lang_wad_path.name}' 时出错: {e}"
                )
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), 0, str(e))
        elif vo_paths:
            logger.warning("语言WAD文件不存在，跳过VO解包。")
            stats.set_wad_info("VO", None, len(vo_paths), 0, "WAD文件不存在")

        root_wad_path = entity_data.get_wad_path("SFX", ctx=ctx)
        if root_wad_path and other_paths:
            other_path_list = list(other_paths)
            try:
                logger.debug(f"正在从 {root_wad_path.name} 解包 {len(other_path_list)} 个SFX/Music文件...")
                wad_obj = _get_wad_instance(root_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(other_path_list, raw=True)
                raw_by_path.update(zip(other_path_list, file_raws, strict=False))
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), len(file_raws))
            except Exception as e:
                logger.opt(exception=bool(getattr(ctx.config, "dev_mode", False))).error(
                    f"解包根WAD文件 '{root_wad_path.name}' 时出错: {e}"
                )
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), 0, str(e))
        elif other_paths:
            logger.warning("根WAD文件不存在，跳过SFX/Music解包。")
            stats.set_wad_info("ROOT", None, len(other_paths), 0, "WAD文件不存在")

        logger.debug("阶段 3: 组装并处理最终数据...")
        # WAD 提取后只拿到“路径 -> 原始字节”，这里再把结果重新挂回对应子实体，
        # 后续输出目录和统计才能继续沿用统一的 sub-entity 语义。
        info_by_path = {**vo_info_by_path, **other_info_by_path}
        audio_by_sub_id: dict[int, dict[str, Any]] = {}

        for path, raw_data in raw_by_path.items():
            sub_info = info_by_path.get(path)
            if not sub_info:
                continue

            sub_id = sub_info["id"]
            if sub_id not in audio_by_sub_id:
                audio_by_sub_id[sub_id] = {"name": sub_info["name"], "files": []}

            audio_by_sub_id[sub_id]["files"].append(
                {
                    "suffix": Path(path).suffix,
                    "raw": raw_data,
                    "type": sub_info["type"],
                    "source_path": path,
                }
            )

        total_assembled_files = sum(len(sub_data["files"]) for sub_data in audio_by_sub_id.values())
        stats.record_assembly_stats(len(audio_by_sub_id), total_assembled_files)
        logger.debug(f"音频文件解包完成，共 {len(audio_by_sub_id)} 个子实体")

        for sub_id, sub_data in audio_by_sub_id.items():
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
                # 输出布局是“子实体目录 + 音频类型”，因此这里先按 audio_type 聚合，
                # 再一次性生成目标目录，避免同一目录反复判断与创建。
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
        component = get_entity_path_component(entity_data.entity_type, entity_data.entity_id)
        report_filename = f"_{component}_metadata.yaml"
        report_path = ctx.report_path / reader.version / get_output_dir_name(entity_data.entity_type) / report_filename
        report_path.parent.mkdir(parents=True, exist_ok=True)
        stats.save_concise_report_to_yaml(report_path)
    except Exception as e:
        logger.debug(f"保存报告文件失败: {e}")

    return stats


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
        get_entity_path_component(entity_data.entity_type, entity_data.entity_id),
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )

    if entity_data.entity_type == "champion":
        sub_folder = format_sub_entity_folder_name(sub_id, sub_name)
        return Path(entity_dir) / entity_folder / sub_folder

    return Path(entity_dir) / entity_folder


def _build_entity_audio_roots(
    entity_data: AudioEntityData,
    version: str,
    *,
    ctx: AppContext,
) -> tuple[Path, ...]:
    """根据输出布局解析实体级音频根目录集合。

    Args:
        entity_data: 已解析的实体数据。
        version: 当前数据版本号。
        ctx: 运行时上下文。

    Returns:
        tuple[Path, ...]: 当前实体对应的一个或多个音频输入根目录。
    """
    audio_root = ctx.audio_path / version
    entity_dir = get_output_dir_name(entity_data.entity_type)
    entity_folder = format_entity_folder_name(
        get_entity_path_component(entity_data.entity_type, entity_data.entity_id),
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )

    if ctx.group_by_type:
        return tuple(audio_root / audio_type / entity_dir / entity_folder for audio_type in ctx.include_types)

    return (audio_root / entity_dir / entity_folder,)


def resolve_entity_audio_roots(
    entity_type: str,
    entity_id: int | str,
    reader: DataReader,
    *,
    ctx: AppContext,
) -> tuple[Path, ...]:
    """解析实体级 WAV 转码输入根目录。

    Args:
        entity_type: 实体类型，例如 ``champion`` 或 ``map``。
        entity_id: 实体 ID 或 resource-pack key。
        reader: 数据读取器。
        ctx: 运行时上下文。

    Returns:
        tuple[Path, ...]: 当前实体对应的音频输入根目录集合。
    """
    entity_data = AudioEntityData.from_entity(
        entity_type,
        entity_id,
        reader,
        ctx=ctx,
    )
    return _build_entity_audio_roots(entity_data, reader.version, ctx=ctx)


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
        # base_path 保持可注入，便于测试和未来镜像目录复用；
        # 默认仍然以 AppContext 的音频根目录为准。
        base_path = ctx.audio_path

    relative_path = _generate_relative_path(entity_data, sub_id)
    if ctx.group_by_type:
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
    persisted_artifact_callback: Callable[[Path], None] | None = None,
) -> EntityUnpackStats:
    """按英雄 ID 解包音频。

    Args:
        champion_id: 英雄 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。
        persisted_artifact_callback: 非 WEM 解包产物落盘后的内部回调。

    Returns:
        保持现有报告 schema 的实体解包统计。
    """
    try:
        entity_data = AudioEntityData.from_entity(
            "champion",
            champion_id,
            reader,
            ctx=ctx,
        )
        stats = unpack_entity(
            entity_data,
            reader,
            wad_cache=wad_cache,
            cache_lock=cache_lock,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
        )
        attach_bp_vo(
            entity_data,
            reader,
            ctx=ctx,
            persisted_artifact_callback=persisted_artifact_callback,
        )
        return stats
    except ValueError as e:
        # 显式记录边界错误后向上抛出，交由 batch 统一计入失败计数；
        # 不在此处吞掉返回 None，否则失败会被误判为成功（见 AGENTS.project.md 日志硬规则）。
        logger.error(str(e))
        raise


def unpack_map(  # noqa: PLR0913
    map_id: int,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> EntityUnpackStats:
    """按地图 ID 解包音频。

    Args:
        map_id: 地图 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。

    Returns:
        保持现有报告 schema 的实体解包统计。
    """
    try:
        entity_data = AudioEntityData.from_entity(
            "map",
            map_id,
            reader,
            ctx=ctx,
        )
        stats = unpack_entity(
            entity_data,
            reader,
            wad_cache=wad_cache,
            cache_lock=cache_lock,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
        )
        return stats
    except ValueError as e:
        # 显式记录边界错误后向上抛出，交由 batch 统一计入失败计数；
        # 不在此处吞掉返回 None，否则失败会被误判为成功（见 AGENTS.project.md 日志硬规则）。
        logger.error(str(e))
        raise


def unpack_resource_pack(  # noqa: PLR0913
    key: str,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> EntityUnpackStats:
    """按 resource-pack stable key 解包音频。

    Args:
        key: canonical resource-pack key。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
        ctx: 运行时上下文。
        persisted_wem_callback: WEM 落盘后的附加回调。

    Returns:
        保持现有报告 schema 的实体解包统计。

    Raises:
        ValueError: resource-pack artifact 或绑定无效时抛出。
    """
    try:
        entity_data = AudioEntityData.from_entity(
            "resource_pack",
            key,
            reader,
            ctx=ctx,
        )
        stats = unpack_entity(
            entity_data,
            reader,
            wad_cache=wad_cache,
            cache_lock=cache_lock,
            ctx=ctx,
            persisted_wem_callback=persisted_wem_callback,
        )
        return stats
    except ValueError as exc:
        logger.error(str(exc))
        raise
