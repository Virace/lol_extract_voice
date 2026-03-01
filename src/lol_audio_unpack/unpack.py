# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 12:27
# @Update  : 2025/8/7 11:28
# @Detail  : 解包音频


import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import AudioEntityData, generate_champion_tasks, generate_map_tasks
from lol_audio_unpack.utils.common import sanitize_filename
from lol_audio_unpack.utils.config import config
from lol_audio_unpack.utils.logging import performance_monitor
from lol_audio_unpack.utils.path_constants import (
    format_entity_folder_name,
    format_sub_entity_folder_name,
    get_output_dir_name,
)
from lol_audio_unpack.utils.stats import FileProcessResult, ProcessingStatsContext

# todo: ID6, 厄加特, 6009, 西部魔影 厄加特, ASSETS/Sounds/Wwise2016/SFX/Characters/Urgot/Skins/Skin09/Urgot_Skin09_VO_audio.bnk, 该文件在根WAD
# todo: ID62, 孙悟空，62007, 战斗学院 孙悟空, ASSETS/Sounds/Wwise2016/SFX/Characters/MonkeyKing/Skins/Skin07/MonkeyKing_Skin07_VO_audio.bnk, 该文件在根WAD


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
def unpack_audio_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
) -> None:
    """解包单个实体音频（英雄或地图）。

    Args:
        entity_data: 音频实体数据。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。

    Raises:
        ValueError: 实体数据无效时抛出。
    """
    language = config.GAME_REGION  # 决定解包哪种语言的音频
    audio_path = config.AUDIO_PATH / reader.version
    if not audio_path.exists():
        audio_path.mkdir(parents=True, exist_ok=True)

    # 使用统计上下文管理器，自动处理统计的开始和结束
    stats_context = ProcessingStatsContext(
        entity_data, reader.version, language, config.INCLUDE_TYPE, config.EXCLUDE_TYPE
    )
    with stats_context as stats:
        logger.info(f"解包 {entity_data.entity_name} (ID:{entity_data.entity_id})")

        # --- 阶段 1: 收集所有需要解包的音频文件路径 ---
        logger.debug("阶段 1: 收集所有需要解包的音频文件路径...")

        # VO（语音）文件通常存储在特定语言的WAD文件中
        vo_paths_to_extract = set()
        vo_path_to_sub_info_map = {}
        # SFX（音效）和Music（音乐）文件通常存储在根WAD文件中
        other_paths_to_extract = set()
        other_path_to_sub_info_map = {}

        # 统计子实体信息
        stats.total_sub_entities = len(entity_data.sub_entities)

        # 直接遍历实体的所有子实体（皮肤或地图）
        for sub_id, sub_data in entity_data.sub_entities.items():
            sub_info = entity_data.get_sub_entity_info(sub_id)
            if not sub_info:
                logger.warning(f"子实体ID {sub_id} 信息不完整，跳过处理")
                stats.record_sub_entity_skipped(sub_id, "信息不完整")
                continue

            stats.processed_sub_entities += 1
            sub_name = sub_info["name"]
            sub_id_int = sub_info["id"]

            # 遍历该子实体的所有音频类别（如VO、SFX等）
            for category, banks_list in sub_data["categories"].items():
                # 通过类别名称判断音频类型（VO/SFX/MUSIC）
                audio_type = reader.get_audio_type(category)

                if audio_type in config.EXCLUDE_TYPE:
                    continue

                # 创建包含子实体信息和音频类型的字典，用于后续文件组织
                sub_info_with_type = {"id": sub_id_int, "name": sub_name, "type": audio_type}

                # 根据音频类型分别处理，VO文件和其他类型文件存储在不同WAD中
                if audio_type == config.AUDIO_TYPE_VO:
                    for bank in banks_list:  # banks_list是合集列表
                        for path in bank:  # 每个合集包含多个文件路径
                            vo_paths_to_extract.add(path)
                            vo_path_to_sub_info_map[path] = sub_info_with_type
                else:  # SFX 和 MUSIC
                    for bank in banks_list:  # banks_list是合集列表
                        for path in bank:  # 每个合集包含多个文件路径
                            other_paths_to_extract.add(path)
                            other_path_to_sub_info_map[path] = sub_info_with_type

        # 记录阶段1的统计信息
        stats.vo_paths_count = len(vo_paths_to_extract)
        stats.sfx_music_paths_count = len(other_paths_to_extract)

        # 检查是否收集到了任何需要处理的音频文件
        if not vo_paths_to_extract and not other_paths_to_extract:
            logger.warning(
                f"{entity_data.entity_type} '{entity_data.entity_name}' 未找到任何需要解包的音频文件 (检查排除类型配置)。"
            )
            return

        # --- 阶段 2: 根据不同WAD文件，批量解包 ---
        logger.debug("阶段 2: 开始批量解包WAD文件...")
        path_to_raw_data_map = {}

        # 2.1 从特定语言的WAD文件中解包VO（语音）文件
        lang_wad_path = entity_data.get_wad_path("VO")
        if lang_wad_path and vo_paths_to_extract:
            vo_path_list = list(vo_paths_to_extract)  # 无需排序（WAD.extract保证顺序）
            try:
                logger.debug(f"正在从 {lang_wad_path.name} 解包 {len(vo_path_list)} 个VO文件...")
                wad_obj = _get_wad_instance(lang_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(vo_path_list, raw=True)
                path_to_raw_data_map.update(zip(vo_path_list, file_raws, strict=False))
                # 记录VO WAD解包成功统计
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), len(file_raws))
            except Exception as e:
                logger.error(f"解包语言WAD文件 '{lang_wad_path.name}' 时出错: {e}")
                logger.debug(traceback.format_exc())
                # 记录VO WAD解包失败统计
                stats.set_wad_info("VO", lang_wad_path, len(vo_path_list), 0, str(e))
        elif vo_paths_to_extract:
            logger.warning("语言WAD文件不存在，跳过VO解包。")
            # 记录WAD不存在的情况
            stats.set_wad_info("VO", None, len(vo_paths_to_extract), 0, "WAD文件不存在")

        # 2.2 从根WAD文件中解包SFX（音效）和Music（音乐）文件
        root_wad_path = entity_data.get_wad_path("SFX")
        if root_wad_path and other_paths_to_extract:
            other_path_list = list(other_paths_to_extract)  # 无需排序（WAD.extract保证顺序）
            try:
                logger.debug(f"正在从 {root_wad_path.name} 解包 {len(other_path_list)} 个SFX/Music文件...")
                wad_obj = _get_wad_instance(root_wad_path, wad_cache=wad_cache, cache_lock=cache_lock)
                file_raws = wad_obj.extract(other_path_list, raw=True)
                path_to_raw_data_map.update(zip(other_path_list, file_raws, strict=False))
                # 记录SFX/Music WAD解包成功统计
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), len(file_raws))
            except Exception as e:
                logger.error(f"解包根WAD文件 '{root_wad_path.name}' 时出错: {e}")
                logger.debug(traceback.format_exc())
                # 记录SFX/Music WAD解包失败统计
                stats.set_wad_info("ROOT", root_wad_path, len(other_path_list), 0, str(e))
        elif other_paths_to_extract:
            logger.warning("根WAD文件不存在，跳过SFX/Music解包。")
            # 记录WAD不存在的情况
            stats.set_wad_info("ROOT", None, len(other_paths_to_extract), 0, "WAD文件不存在")

        # --- 阶段 3: 组装最终数据 ---
        logger.debug("阶段 3: 组装并处理最终数据...")
        path_to_sub_info_map = {**vo_path_to_sub_info_map, **other_path_to_sub_info_map}
        unpacked_audio_data = {}
        raw_data_to_path_map = {}  # 创建反向映射：原始数据到文件路径

        for path, raw_data in path_to_raw_data_map.items():
            raw_data_to_path_map[id(raw_data)] = path
            sub_info = path_to_sub_info_map.get(path)
            if not sub_info:
                continue

            sub_id = sub_info["id"]
            if sub_id not in unpacked_audio_data:
                unpacked_audio_data[sub_id] = {"name": sub_info["name"], "files": []}

            # 创建文件信息字典，包含文件扩展名、原始数据和音频类型
            file_info = {
                "suffix": Path(path).suffix,  # 文件扩展名（如.bnk, .wpk）
                "raw": raw_data,  # 文件的原始二进制数据
                "type": sub_info["type"],  # 音频类型（VO/SFX/MUSIC）
                "source_path": path,  # 源路径信息
            }
            unpacked_audio_data[sub_id]["files"].append(file_info)

        # 记录阶段3的统计信息
        total_assembled_files = sum(len(sub_data["files"]) for sub_data in unpacked_audio_data.values())
        stats.record_assembly_stats(len(unpacked_audio_data), total_assembled_files)

        logger.debug(f"音频文件解包完成，共 {len(unpacked_audio_data)} 个子实体")

        # --- 阶段 4: 保存解包后的文件 ---
        for sub_id, sub_data in unpacked_audio_data.items():
            sub_name = sub_data["name"]
            files = sub_data["files"]
            sub_id_str = str(sub_id)

            # 按音频类型对文件进行分组，方便后续按类型创建不同目录
            files_by_type = {}
            for file_info in files:
                audio_type = file_info["type"]
                if audio_type not in files_by_type:
                    files_by_type[audio_type] = []
                files_by_type[audio_type].append(file_info)

            # 遍历每种音频类型的文件组
            for audio_type, files_in_type in files_by_type.items():
                output_path = generate_output_path(entity_data, sub_id_str, audio_type, audio_path)
                output_path.mkdir(parents=True, exist_ok=True)

                logger.debug(f"处理 {sub_name} ({audio_type}) - {len(files_in_type)} 个文件")

                for file_info in files_in_type:
                    file_size = len(file_info["raw"]) if file_info["raw"] else 0
                    source_path = file_info.get("source_path", "未知路径")

                    logger.trace(f"  - 类型: {file_info['suffix']}, 大小: {file_size} 字节")

                    if file_size == 0:
                        # 记录空容器统计
                        stats.record_file_result(
                            sub_id, sub_name, audio_type, FileProcessResult.EMPTY_CONTAINER, source_path=source_path
                        )
                        continue

                    if file_info["suffix"] == ".bnk":
                        try:
                            bnk = BNK(file_info["raw"])
                            for file in bnk.extract_files():
                                if not file.data:
                                    logger.warning(f"BNK, 文件 {file.id} 没有数据，跳过保存")
                                    # 记录空子文件统计
                                    stats.record_file_result(
                                        sub_id, sub_name, audio_type, FileProcessResult.EMPTY_SUBFILE
                                    )
                                    continue

                                file.save_file(output_path / f"{file.id}.wem")
                                # 记录成功统计
                                stats.record_file_result(sub_id, sub_name, audio_type, FileProcessResult.SUCCESS)
                        except Exception as e:
                            logger.warning(f"处理BNK文件失败: {e} | 文件路径: {source_path}")
                            # 记录解析错误统计
                            error_info = {"path": source_path, "error": str(e), "type": "BNK"}
                            stats.record_file_result(
                                sub_id, sub_name, audio_type, FileProcessResult.PARSE_ERROR, error_info=error_info
                            )
                    elif file_info["suffix"] == ".wpk":
                        try:
                            wpk = WPK(file_info["raw"])
                            for file in wpk.extract_files():
                                file.save_file(output_path / f"{file.filename}")
                                # 记录成功统计
                                stats.record_file_result(sub_id, sub_name, audio_type, FileProcessResult.SUCCESS)
                        except Exception as e:
                            logger.warning(f"处理WPK文件失败: {e} | 文件路径: {source_path}")
                            # 记录解析错误统计
                            error_info = {"path": source_path, "error": str(e), "type": "WPK"}
                            stats.record_file_result(
                                sub_id, sub_name, audio_type, FileProcessResult.PARSE_ERROR, error_info=error_info
                            )
                    else:
                        # 如果遇到未知的文件类型，记录警告和文件路径
                        logger.warning(f"未知的文件类型: {file_info['suffix']} | 文件路径: {source_path}")
                        # 记录未知类型统计
                        error_info = {
                            "path": source_path,
                            "error": f"未知文件类型: {file_info['suffix']}",
                            "type": "UNKNOWN",
                        }
                        stats.record_file_result(
                            sub_id, sub_name, audio_type, FileProcessResult.UNKNOWN_TYPE, error_info=error_info
                        )

    # === 统计结果处理 ===
    # with语句块结束后，统计已经完成，现在处理结果

    # 输出简洁的汇总日志
    summary = stats.get_simple_summary()

    if stats.overall_result.value == "success":
        logger.success(summary)
    elif stats.overall_result.value == "warning":
        logger.warning(summary)
    else:
        logger.error(summary)

    # 如果有问题，输出失败文件的详细信息到调试日志
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

    # 保存简洁的YAML报告
    try:
        report_filename = f"_{entity_data.entity_id}_metadata.yaml"

        report_path = (
            config.REPORT_PATH / reader.version / get_output_dir_name(entity_data.entity_type) / report_filename
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        stats.save_concise_report_to_yaml(report_path)
    except Exception as e:
        logger.debug(f"保存报告文件失败: {e}")


def _generate_relative_path(entity_data: AudioEntityData, sub_id: str) -> str:
    """生成相对路径（不包含音频类型）

    :param entity_data: 实体数据
    :param sub_id: 子实体ID（皮肤ID或地图ID）
    :returns: 相对路径字符串
    """
    sub_name = entity_data.sub_entities[sub_id]["name"]
    # 使用统一的小写目录名
    entity_dir = get_output_dir_name(entity_data.entity_type)

    # 使用统一的文件夹命名格式
    entity_folder_name = format_entity_folder_name(
        entity_data.entity_id, entity_data.entity_alias, entity_data.entity_name, entity_data.entity_title
    )

    if entity_data.entity_type == "champion":
        # champions\1·annie·黑暗之女·安妮\1000·基础皮肤
        sub_folder_name = format_sub_entity_folder_name(sub_id, sub_name)
        return f"{entity_dir}\\{entity_folder_name}\\{sub_folder_name}"
    else:  # map
        # maps\11·sr·召唤师峡谷
        return f"{entity_dir}\\{entity_folder_name}"


def generate_output_path(
    entity_data: AudioEntityData, sub_id: str, audio_type: str, base_path: Path | None = None
) -> Path:
    """生成完整的输出路径

    根据 config.GROUP_BY_TYPE 配置决定目录结构：
    - True: audios/VO/champions/1·annie·黑暗之女·安妮/1000·基础皮肤
    - False: audios/champions/1·annie·黑暗之女·安妮/1000·基础皮肤/VO

    :param entity_data: 实体数据
    :param sub_id: 子实体ID（皮肤ID或地图ID）
    :param audio_type: 音频类型（VO/SFX/MUSIC）
    :param base_path: 基础路径，默认使用 config.AUDIO_PATH
    :returns: 完整的输出路径
    """
    if base_path is None:
        base_path = config.AUDIO_PATH

    relative_path = _generate_relative_path(entity_data, sub_id)

    if config.GROUP_BY_TYPE:
        # 方案一：按音频类型优先分组 - audios/音频类型/相对路径
        return base_path / audio_type / relative_path
    else:
        # 方案二：按实体优先分组 - audios/相对路径/音频类型
        return base_path / relative_path / audio_type


def unpack_champion(
    champion_id: int,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
) -> None:
    """按英雄 ID 解包音频。

    Args:
        champion_id: 英雄 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
    """
    try:
        # 创建AudioEntityData实例
        entity_data = AudioEntityData.from_champion(champion_id, reader)
        # 调用通用解包函数
        unpack_audio_entity(entity_data, reader, wad_cache=wad_cache, cache_lock=cache_lock)
    except ValueError as e:
        # 保持与原始函数相同的错误处理方式
        logger.error(str(e))
        return


def unpack_map_audio(
    map_id: int,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
) -> None:
    """按地图 ID 解包音频。

    Args:
        map_id: 地图 ID。
        reader: 已初始化的数据读取器。
        wad_cache: 本轮解包共享 WAD 缓存。
        cache_lock: 多线程场景下的缓存锁。
    """
    try:
        # 创建AudioEntityData实例
        entity_data = AudioEntityData.from_map(map_id, reader)
        # 调用通用解包函数
        unpack_audio_entity(entity_data, reader, wad_cache=wad_cache, cache_lock=cache_lock)
    except ValueError as e:
        # 保持一致的错误处理方式
        logger.error(str(e))
        return


def execute_unpack_tasks(tasks: list[tuple[str, int, str]], reader: DataReader, max_workers: int = 4) -> None:
    """执行批量解包任务。

    Args:
        tasks: 任务元组列表 ``[(entity_type, id, description), ...]``。
        reader: 数据读取器实例。
        max_workers: 最大并发线程数。
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

    logger.info(
        f"开始解包 {total_tasks} 个实体 ({' 和 '.join(summary_parts)})，"
        f"模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )

    wad_cache: dict[Path, WAD] = {}
    cache_lock = threading.Lock() if max_workers > 1 else None

    def unpack_entity(entity_type: str, entity_id: int) -> None:
        """解包单个实体的辅助函数"""
        if entity_type == "champion":
            unpack_champion(entity_id, reader, wad_cache=wad_cache, cache_lock=cache_lock)
        elif entity_type == "map":
            unpack_map_audio(entity_id, reader, wad_cache=wad_cache, cache_lock=cache_lock)
        else:
            raise ValueError(f"未知的实体类型: {entity_type}")

    if max_workers > 1:
        # --- 多线程模式 ---
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(unpack_entity, entity_type, entity_id): (entity_type, entity_id, description)
                for entity_type, entity_id, description in tasks
            }
            completed_count = 0

            for future in as_completed(future_to_task):
                entity_type, entity_id, description = future_to_task[future]
                completed_count += 1

                try:
                    future.result()  # 获取结果，如果函数中出现异常，这里会重新抛出
                    logger.info(f"进度: {completed_count}/{total_tasks} - {description} 解包完成。")
                except Exception as exc:
                    logger.error(f"{description} 解包时发生错误: {exc}")
                    logger.debug(traceback.format_exc())
    else:
        # --- 单线程模式 ---
        completed_count = 0
        for entity_type, entity_id, description in tasks:
            try:
                unpack_entity(entity_type, entity_id)
                completed_count += 1
                logger.info(f"进度: {completed_count}/{total_tasks} - {description} 解包完成。")
            except Exception as exc:
                logger.error(f"{description} 解包时发生错误: {exc}")
                logger.debug(traceback.format_exc())

    end_time = time.time()
    logger.success(f"解包完成: {' 和 '.join(summary_parts)}，耗时 {end_time - start_time:.2f}s")

    # 在所有操作完成后，将收集到的未知分类写入文件
    reader.write_unknown_categories_to_file()


def unpack_audio_all(
    reader: DataReader, max_workers: int = 4, include_champions: bool = True, include_maps: bool = True
) -> None:
    """使用线程池并发解包所有音频文件

    解包所有可用的英雄和地图音频文件。
    通过设置 max_workers=1 可以切换到单线程顺序执行模式。

    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :param max_workers: 使用的最大线程数 (1: 单线程, >1: 多线程)
    :param include_champions: 是否包含英雄解包
    :param include_maps: 是否包含地图解包
    """
    tasks = []

    # 生成英雄任务
    if include_champions:
        champion_tasks = generate_champion_tasks(reader, None)
        tasks.extend(champion_tasks)
        logger.debug(f"已添加 {len(champion_tasks)} 个英雄解包任务")

    # 生成地图任务
    if include_maps:
        map_tasks = generate_map_tasks(reader, None)
        tasks.extend(map_tasks)
        logger.debug(f"已添加 {len(map_tasks)} 个地图解包任务")

    if not tasks:
        logger.warning("没有找到任何需要解包的实体")
        return

    # 执行任务
    execute_unpack_tasks(tasks, reader, max_workers)


def unpack_champions(reader: DataReader, champion_ids: list[int], max_workers: int = 4) -> None:
    """便捷函数：解包指定英雄

    :param reader: 数据读取器
    :param champion_ids: 英雄ID列表
    :param max_workers: 最大工作线程数
    :raises ValueError: 当指定的ID不存在时
    """
    tasks = generate_champion_tasks(reader, champion_ids)
    execute_unpack_tasks(tasks, reader, max_workers)


def unpack_maps(reader: DataReader, map_ids: list[int], max_workers: int = 4) -> None:
    """便捷函数：解包指定地图

    :param reader: 数据读取器
    :param map_ids: 地图ID列表
    :param max_workers: 最大工作线程数
    :raises ValueError: 当指定的ID不存在时
    """
    tasks = generate_map_tasks(reader, map_ids)
    execute_unpack_tasks(tasks, reader, max_workers)
