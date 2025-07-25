# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 12:27
# @Update  : 2025/7/25 10:39
# @Detail  : 解包音频


import os
import traceback
from pathlib import Path

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.Utils.config import config


def unpack_audio(hero_id: int, reader: DataReader):
    """根据英雄ID和已加载的数据读取器解包其音频文件

    :param hero_id: 英雄ID
    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :return: None
    """
    language = config.GAME_REGION
    logger.info(f"开始解包英雄ID {hero_id} 的音频文件，语言: {language}")

    # 步骤1: 读取游戏数据
    champion = reader.get_champion(hero_id)

    if not champion:
        logger.error(f"未找到ID为 {hero_id} 的英雄")
        return

    # 获取英雄别名和名称
    alias = champion.get("alias", "").lower()
    name = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))

    logger.info(f"英雄信息: ID={hero_id}, 别名={alias}, 名称={name}")

    # --- 阶段 1: 确定唯一的WAD文件并收集所有皮肤的VO文件路径 ---
    logger.info("阶段 1: 收集所有皮肤的VO文件路径...")

    # 为单个英雄和语言确定唯一的WAD文件
    wad_file = champion.get("wad", {}).get(language)
    if not wad_file:
        logger.error(f"在英雄 '{alias}' 的数据中未找到语言 '{language}' 对应的WAD文件。")
        return
    wad_path = config.GAME_PATH / wad_file
    if not wad_path.exists():
        logger.error(f"WAD文件不存在: {wad_path}。无法继续解包。")
        return

    # paths_to_extract: {"file_a", "file_b", "file_c"}
    paths_to_extract = set()
    # path_to_skin_info_map: { "file_a": {"id": 1, "name": "皮肤1"}, "file_b": {"id": 1, "name": "皮肤1"} }
    path_to_skin_info_map = {}

    for skin in champion.get("skins", []):
        skin_name_raw = skin.get("skinNames").get(language, skin.get("skinNames").get("default", ""))
        is_base_skin = skin.get("isBase", False)
        # 根据用户要求，基础皮肤使用固定名称 "基础皮肤"
        skin_name = "基础皮肤" if is_base_skin else skin_name_raw
        skin_id = skin.get("id")

        banks = reader.get_skin_bank(skin_id)
        if not banks:
            continue

        for key, banks_list in banks.items():
            if "VO" in key:
                for bank in banks_list:
                    for path in bank:
                        paths_to_extract.add(path)
                        path_to_skin_info_map[path] = {"id": skin_id, "name": skin_name}

    if not paths_to_extract:
        logger.warning(f"英雄 '{name}' 未找到任何需要解包的VO音频文件。")
        return

    # --- 阶段 2: 对唯一的WAD文件执行一次解包操作 ---
    logger.info("阶段 2: 开始批量解包WAD文件...")
    path_to_raw_data_map = {}
    path_list = sorted(list(paths_to_extract))  # 排序以保证顺序

    try:
        logger.info(f"正在从 {wad_path.name} 解包 {len(path_list)} 个文件...")
        file_raws = WAD(wad_path).extract(path_list, raw=True)
        # 将解包后的数据与原始路径对应起来
        path_to_raw_data_map.update(zip(path_list, file_raws, strict=False))
    except Exception as e:
        logger.error(f"解包WAD文件 '{wad_path.name}' 时出错: {e}")
        logger.debug(traceback.format_exc())
        return

    # --- 阶段 3: 组装最终数据 ---
    logger.info("阶段 3: 组装并处理最终数据...")
    unpacked_vo_data = {}
    for path, raw_data in path_to_raw_data_map.items():
        skin_info = path_to_skin_info_map.get(path)
        if not skin_info:
            continue

        skin_id = skin_info["id"]
        # 确保皮肤条目在结果字典中存在
        if skin_id not in unpacked_vo_data:
            unpacked_vo_data[skin_id] = {"name": skin_info["name"], "files": []}

        file_info = {
            "suffix": Path(path).suffix,
            "raw": raw_data,
        }
        unpacked_vo_data[skin_id]["files"].append(file_info)

    # 最终处理完成
    logger.success(f"所有皮肤的VO文件解包完成，共 {len(unpacked_vo_data)} 个皮肤。开始处理解包后的文件...")

    # --- 阶段 4: 保存解包后的文件 ---
    hero_path = config.AUDIO_PATH / "Champions" / f"{hero_id}·{alias}·{name}"

    for skin_id, skin_data in unpacked_vo_data.items():
        skin_name = skin_data["name"]
        files = skin_data["files"]

        # 创建一个文件夹，用来存放解包后的文件
        skin_path = hero_path / f"{skin_id}·{skin_name}"
        skin_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"正在为皮肤 '{skin_name}' (ID: {skin_id}) 保存 {len(files)} 个文件至 {skin_path}")

        for file_info in files:
            file_size = len(file_info["raw"]) if file_info["raw"] else 0

            logger.debug(f"  - 类型: {file_info['suffix']}, 大小: {file_size} 字节")

            if file_size == 0:
                continue

            # 判断文件类型
            if file_info["suffix"] == ".bnk":
                # 解包bnk文件
                try:
                    bnk = BNK(file_info["raw"])
                    for file in bnk.get_data_files():
                        file.save_file(f"{skin_path}/{file.filename}")
                        logger.trace(f"BNK, 已解包 {file.filename} 文件")
                except Exception as e:
                    logger.warning(f"处理BNK文件失败: {e}")
            elif file_info["suffix"] == ".wpk":
                # 解包wpk文件
                try:
                    wpk = WPK(file_info["raw"])
                    for file in wpk.get_files_data():
                        file.save_file(f"{skin_path}/{file.filename}")
                        logger.trace(f"WPK, 已解包 {file.filename} 文件")
                except Exception as e:
                    logger.warning(f"处理WPK文件失败: {e}")
            else:
                logger.warning(f"未知的文件类型: {file_info['suffix']}")
