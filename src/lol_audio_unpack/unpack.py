# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 12:27
# @Update  : 2025/7/25 5:17
# @Detail  : 解包音频


import os
import traceback
from pathlib import Path

from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.manager import BinUpdater, DataReader, DataUpdater
from lol_audio_unpack.Utils.config import config


def unpack_audio(hero_id: int, language: str = "zh_CN"):
    """根据英雄ID解包其音频文件

    :param hero_id: 英雄ID
    :param language: 语言代码，默认为zh_CN
    :return: None
    """
    logger.info(f"开始解包英雄ID {hero_id} 的音频文件，语言: {language}")

    # 步骤1: 更新游戏数据
    data_updater = DataUpdater()
    bin_updater = BinUpdater()
    data_updater.check_and_update()
    # bin_updater.update()

    # 步骤2: 读取游戏数据
    reader = DataReader()
    champion = reader.get_champion(hero_id)

    if not champion:
        logger.error(f"未找到ID为 {hero_id} 的英雄")
        return

    # 获取英雄别名和名称
    alias = champion.get("alias", "").lower()
    name = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))

    logger.info(f"英雄信息: ID={hero_id}, 别名={alias}, 名称={name}")

    # 在config.TEMP_PATH下创建一个文件夹，用来存放bnk、wpk等临时文件解包后删除
    temp_path = config.TEMP_PATH / f"{hero_id}"
    temp_path.mkdir(parents=True, exist_ok=True)

    # --- 阶段 1: 收集所有需要解包的文件路径，并按WAD文件分组 ---
    logger.info("阶段 1: 收集所有皮肤的VO文件路径...")
    # wad_to_paths_map: { "wad_path_1": {"file_a", "file_b"}, "wad_path_2": {"file_c"} }
    wad_to_paths_map = {}
    # path_to_skin_map: { "file_a": "皮肤名1", "file_b": "皮肤名1", "file_c": "皮肤名2" }
    path_to_skin_map = {}

    for skin in champion.get("skins", []):
        skin_name = skin.get("skinNames").get(language, skin.get("skinNames").get("default", ""))
        skin_id = skin.get("id")

        wad_file = champion.get("wad", {}).get(language)
        if not wad_file:
            logger.warning(f"语言 '{language}' WAD文件未找到，跳过皮肤 '{skin_name}'")
            continue
        wad_path = config.GAME_PATH / wad_file

        banks = reader.get_skin_bank(skin_id)
        if not banks:
            continue

        # 确保WAD路径在map中存在
        wad_to_paths_map.setdefault(wad_path, set())

        for key, banks_list in banks.items():
            if "VO" in key:
                for bank in banks_list:
                    for path in bank:
                        wad_to_paths_map[wad_path].add(path)
                        path_to_skin_map[path] = skin_name

    # --- 阶段 2: 对每个WAD文件执行一次解包操作 ---
    logger.info("阶段 2: 开始批量解包WAD文件...")
    # path_to_raw_data_map: { "file_a": b"...", "file_b": b"..." }
    path_to_raw_data_map = {}
    for wad_path, paths_to_extract in wad_to_paths_map.items():
        if not paths_to_extract:
            continue

        path_list = sorted(list(paths_to_extract))  # 排序以保证顺序
        try:
            logger.info(f"正在从 {wad_path.name} 解包 {len(path_list)} 个文件...")
            file_raws = WAD(wad_path).extract(path_list, raw=True)
            # 将解包后的数据与原始路径对应起来
            path_to_raw_data_map.update(zip(path_list, file_raws, strict=False))
        except Exception as e:
            logger.error(f"解包WAD文件 '{wad_path.name}' 时出错: {e}")
            logger.debug(traceback.format_exc())

    # --- 阶段 3: 组装最终数据 ---
    logger.info("阶段 3: 组装最终数据结构...")
    unpacked_vo_data = {}
    for path, raw_data in path_to_raw_data_map.items():
        skin_name = path_to_skin_map.get(path)
        if not skin_name:
            continue

        # 确保皮肤条目在结果字典中存在
        unpacked_vo_data.setdefault(skin_name, [])

        file_info = {
            "path": path,
            "suffix": Path(path).suffix,
            "raw": raw_data,
        }
        unpacked_vo_data[skin_name].append(file_info)

    # 最终处理完成
    logger.success("所有皮肤的VO文件解包和映射完成。")

    # 你可以在这里继续处理 unpacked_vo_data，例如区分 .bnk 和 .wpk 文件
    for skin_name, files in unpacked_vo_data.items():
        logger.info(f"为皮肤 '{skin_name}' 解包了 {len(files)} 个文件:")
        for file_info in files:
            file_size = len(file_info["raw"]) if file_info["raw"] else 0
            logger.debug(f"  - 路径: {file_info['path']}, 类型: {file_info['suffix']}, 大小: {file_size} 字节")
