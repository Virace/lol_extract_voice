# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 12:27
# @Update  : 2025/7/30 7:55
# @Detail  : 解包音频


import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.utils.common import sanitize_filename
from lol_audio_unpack.utils.config import config


def unpack_audio(hero_id: int, reader: DataReader):
    """根据英雄ID和已加载的数据读取器解包其音频文件

    :param hero_id: 英雄ID
    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :return: None
    """
    language = config.GAME_REGION
    logger.info(f"开始解包英雄ID {hero_id} 的音频文件，语言: {language}")

    # 读取并处理排除配置
    excluded_types = {t.strip().upper() for t in config.EXCLUDE_TYPE if t.strip()}
    logger.info(
        f"将要解包的音频类型 (已排除: {excluded_types if excluded_types else '无'}): "
        f"{[t for t in [reader.AUDIO_TYPE_VO, reader.AUDIO_TYPE_SFX, reader.AUDIO_TYPE_MUSIC] if t not in excluded_types]}"
    )

    # 步骤1: 读取游戏数据
    champion = reader.get_champion(hero_id)

    if not champion:
        logger.error(f"未找到ID为 {hero_id} 的英雄")
        return

    # 获取英雄别名和名称
    alias = champion.get("alias", "").lower()
    name = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))

    logger.info(f"英雄信息: ID={hero_id}, 别名={alias}, 名称={name}")

    # --- 阶段 1: 收集所有需要解包的音频文件路径 ---
    logger.info("阶段 1: 收集所有需要解包的音频文件路径...")

    # 分类存放不同类型的路径和映射信息
    # VO 文件通常在特定语言的 WAD 中
    vo_paths_to_extract = set()
    vo_path_to_skin_info_map = {}
    # SFX 和 Music 文件通常在根 WAD 中
    other_paths_to_extract = set()
    other_path_to_skin_info_map = {}

    for skin in champion.get("skins", []):
        skin_name_raw = skin.get("skinNames").get(language, skin.get("skinNames").get("default", ""))
        is_base_skin = skin.get("isBase", False)
        skin_name = "基础皮肤" if is_base_skin else skin_name_raw
        skin_id = skin.get("id")

        banks = reader.get_skin_bank(skin_id)
        if not banks:
            continue

        for category, banks_list in banks.items():
            audio_type = reader.get_audio_type(category)

            # 根据配置排除类型
            if audio_type in excluded_types:
                continue

            # 为路径关联上皮肤信息和音频类型
            skin_info_with_type = {"id": skin_id, "name": skin_name, "type": audio_type}

            if audio_type == reader.AUDIO_TYPE_VO:
                for bank in banks_list:
                    for path in bank:
                        vo_paths_to_extract.add(path)
                        vo_path_to_skin_info_map[path] = skin_info_with_type
            else:  # SFX 和 MUSIC
                for bank in banks_list:
                    for path in bank:
                        other_paths_to_extract.add(path)
                        other_path_to_skin_info_map[path] = skin_info_with_type

    if not vo_paths_to_extract and not other_paths_to_extract:
        logger.warning(f"英雄 '{name}' 未找到任何需要解包的音频文件 (检查排除类型配置)。")
        return

    # --- 阶段 2: 根据不同WAD文件，批量解包 ---
    logger.info("阶段 2: 开始批量解包WAD文件...")
    path_to_raw_data_map = {}

    # 2.1 从特定语言的 WAD 解包 VO
    lang_wad_file = champion.get("wad", {}).get(language)
    if lang_wad_file and vo_paths_to_extract:
        lang_wad_path = config.GAME_PATH / lang_wad_file
        if lang_wad_path.exists():
            vo_path_list = sorted(list(vo_paths_to_extract))
            try:
                logger.info(f"正在从 {lang_wad_path.name} 解包 {len(vo_path_list)} 个VO文件...")
                file_raws = WAD(lang_wad_path).extract(vo_path_list, raw=True)
                path_to_raw_data_map.update(zip(vo_path_list, file_raws, strict=False))
            except Exception as e:
                logger.error(f"解包语言WAD文件 '{lang_wad_path.name}' 时出错: {e}")
                logger.debug(traceback.format_exc())
        else:
            logger.warning(f"语言WAD文件不存在: {lang_wad_path}, 跳过VO解包。")

    # 2.2 从根 WAD 解包 SFX 和 Music
    root_wad_file = champion.get("wad", {}).get("root")
    if root_wad_file and other_paths_to_extract:
        root_wad_path = config.GAME_PATH / root_wad_file
        if root_wad_path.exists():
            other_path_list = sorted(list(other_paths_to_extract))
            try:
                logger.info(f"正在从 {root_wad_path.name} 解包 {len(other_path_list)} 个SFX/Music文件...")
                file_raws = WAD(root_wad_path).extract(other_path_list, raw=True)
                path_to_raw_data_map.update(zip(other_path_list, file_raws, strict=False))
            except Exception as e:
                logger.error(f"解包根WAD文件 '{root_wad_path.name}' 时出错: {e}")
                logger.debug(traceback.format_exc())
        else:
            logger.warning(f"根WAD文件不存在: {root_wad_path}, 跳过SFX/Music解包。")

    # --- 阶段 3: 组装最终数据 ---
    logger.info("阶段 3: 组装并处理最终数据...")
    path_to_skin_info_map = {**vo_path_to_skin_info_map, **other_path_to_skin_info_map}
    unpacked_audio_data = {}
    for path, raw_data in path_to_raw_data_map.items():
        skin_info = path_to_skin_info_map.get(path)
        if not skin_info:
            continue

        skin_id = skin_info["id"]
        # 确保皮肤条目在结果字典中存在
        if skin_id not in unpacked_audio_data:
            unpacked_audio_data[skin_id] = {"name": skin_info["name"], "files": []}

        file_info = {
            "suffix": Path(path).suffix,
            "raw": raw_data,
            "type": skin_info["type"],  # 直接传递音频类型
        }
        unpacked_audio_data[skin_id]["files"].append(file_info)

    # 最终处理完成
    logger.success(f"所有皮肤的音频文件解包完成，共 {len(unpacked_audio_data)} 个皮肤。开始处理解包后的文件...")

    # --- 阶段 4: 保存解包后的文件 ---
    # 清理名称中的非法字符
    safe_alias = sanitize_filename(alias)
    safe_name = sanitize_filename(name)
    hero_path_base = config.AUDIO_PATH
    hero_path_segment = Path("Champions") / f"{hero_id}·{safe_alias}·{safe_name}"

    for skin_id, skin_data in unpacked_audio_data.items():
        skin_name = skin_data["name"]
        files = skin_data["files"]
        safe_skin_name = sanitize_filename(skin_name, "'")
        skin_path_segment = Path(f"{skin_id}·{safe_skin_name}")

        # 为该皮肤创建一个文件类型 -> 文件列表的映射，方便后续按类型分目录
        files_by_type = {}
        for file_info in files:
            audio_type = file_info["type"]
            if audio_type not in files_by_type:
                files_by_type[audio_type] = []
            files_by_type[audio_type].append(file_info)

        for audio_type, files_in_type in files_by_type.items():
            # 根据 config.GROUP_BY_TYPE 动态构建输出路径
            if config.GROUP_BY_TYPE:
                # 方案一： audios/类型/Champions/英雄/皮肤
                output_path = hero_path_base / audio_type / hero_path_segment / skin_path_segment
            else:
                # 方案二： audios/Champions/英雄/皮肤/类型
                output_path = hero_path_base / hero_path_segment / skin_path_segment / audio_type

            output_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"正在处理皮肤 '{skin_name}' (ID: {skin_id}, 类型: {audio_type}) , 工作目录: {output_path}")

            success_count, container_skipped_count, subfile_skipped_count, error_count = 0, 0, 0, 0
            for file_info in files_in_type:
                file_size = len(file_info["raw"]) if file_info["raw"] else 0

                logger.debug(f"  - 类型: {file_info['suffix']}, 大小: {file_size} 字节")

                if file_size == 0:
                    container_skipped_count += 1
                    continue

                # 判断文件类型
                if file_info["suffix"] == ".bnk":
                    # 解包bnk文件
                    try:
                        bnk = BNK(file_info["raw"])
                        for file in bnk.extract_files():
                            if not file.data:
                                logger.warning(f"BNK, 文件 {file.id} 没有数据，跳过保存")
                                subfile_skipped_count += 1
                                continue

                            file.save_file(output_path / f"{file.id}.wem")
                            logger.trace(f"BNK, 已解包 {file.id} 文件")
                            success_count += 1
                    except Exception as e:
                        logger.warning(f"处理BNK文件失败: {e}")
                        error_count += 1
                elif file_info["suffix"] == ".wpk":
                    # 解包wpk文件
                    try:
                        wpk = WPK(file_info["raw"])
                        for file in wpk.extract_files():
                            file.save_file(output_path / f"{file.filename}")
                            logger.trace(f"WPK, 已解包 {file.filename} 文件")
                            success_count += 1
                    except Exception as e:
                        logger.warning(f"处理WPK文件失败: {e}")
                        error_count += 1
                else:
                    logger.warning(f"未知的文件类型: {file_info['suffix']}")
                    error_count += 1

            # 输出处理统计
            summary_message = f"皮肤 '{skin_name}' (类型: {audio_type}) 处理完成。结果: 成功 {success_count} 个"
            details = []
            if subfile_skipped_count > 0:
                details.append(f"跳过空子文件 {subfile_skipped_count} 个")
            if container_skipped_count > 0:
                details.append(f"跳过空容器 {container_skipped_count} 个")
            if error_count > 0:
                details.append(f"处理失败 {error_count} 个")

            if details:
                summary_message += f" ({', '.join(details)})"
            summary_message += "."

            if error_count > 0 or container_skipped_count > 0:
                logger.warning(summary_message)
            else:
                logger.success(summary_message)


def unpack_audio_all(reader: DataReader, max_workers: int = 4):
    """
    使用线程池并发解包所有英雄的音频文件。

    通过设置 max_workers=1 可以切换到单线程顺序执行模式，以对比性能。

    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :param max_workers: 使用的最大线程数 (1: 单线程, >1: 多线程)
    """
    start_time = time.time()
    champions = reader.get_champions()
    champion_ids = [champion.get("id") for champion in champions]
    total_heroes = len(champion_ids)
    logger.info(
        f"开始解包所有 {total_heroes} 个英雄，模式: {'多线程' if max_workers > 1 else '单线程'} (workers: {max_workers})"
    )

    if max_workers > 1:
        # --- 多线程模式 ---
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_hero = {executor.submit(unpack_audio, hero_id, reader): hero_id for hero_id in champion_ids}
            completed_count = 0
            for future in as_completed(future_to_hero):
                hero_id = future_to_hero[future]
                completed_count += 1
                try:
                    future.result()  # 获取结果，如果函数中出现异常，这里会重新抛出
                    logger.info(f"进度: {completed_count}/{total_heroes} - 英雄ID {hero_id} 解包完成。")
                except Exception as exc:
                    logger.error(f"英雄ID {hero_id} 解包时发生错误: {exc}")
                    logger.debug(traceback.format_exc())
    else:
        # --- 单线程模式 ---
        completed_count = 0
        for hero_id in champion_ids:
            try:
                unpack_audio(hero_id, reader)
                completed_count += 1
                logger.info(f"进度: {completed_count}/{total_heroes} - 英雄ID {hero_id} 解包完成。")
            except Exception as exc:
                logger.error(f"英雄ID {hero_id} 解包时发生错误: {exc}")
                logger.debug(traceback.format_exc())

    end_time = time.time()
    logger.success(f"全部 {total_heroes} 个英雄解包完成，总耗时: {end_time - start_time:.2f} 秒。")

    # 在所有操作完成后，将收集到的未知分类写入文件
    reader.write_unknown_categories_to_file()
