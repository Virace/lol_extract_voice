# 🐍 If the implementation is hard to explain, it's a bad idea.
# 🐼 很难解释的，必然是坏方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/23 12:27
# @Update  : 2025/8/1 6:05
# @Detail  : 解包音频


import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from league_tools.formats import BNK, WAD, WPK
from loguru import logger

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.utils.common import sanitize_filename
from lol_audio_unpack.utils.config import config

# todo: ID6, 厄加特, 6009, 西部魔影 厄加特, ASSETS/Sounds/Wwise2016/SFX/Characters/Urgot/Skins/Skin09/Urgot_Skin09_VO_audio.bnk, 该文件在根WAD
# todo: ID62, 孙悟空，62007, 战斗学院 孙悟空, ASSETS/Sounds/Wwise2016/SFX/Characters/MonkeyKing/Skins/Skin07/MonkeyKing_Skin07_VO_audio.bnk, 该文件在根WAD

# todo: ID11, 召唤师峡谷, ASSETS/Sounds/Wwise2016/VO/en_US/Shared/MISC_Emotes_VO_audio.wpk, 该文件在Common WAD中


@dataclass
class AudioEntityData:
    """音频实体统一数据结构

    :param entity_id: 实体ID（英雄ID或地图ID）
    :param entity_name: 实体名称（英雄名或地图名）
    :param entity_alias: 实体别名（英雄alias或地图mapStringId）
    :param entity_type: 实体类型（"champion" 或 "map"）
    :param sub_entities: 子实体数据（皮肤数据或地图本身）
    :param wad_root: 根WAD文件路径（用于SFX/Music）
    :param wad_language: 语言WAD文件路径（用于VO），None表示无语言WAD
    """

    entity_id: str
    entity_name: str
    entity_alias: str
    entity_type: str  # "champion" | "map"
    sub_entities: dict[str, dict[str, Any]]
    wad_root: str
    wad_language: str | None = None

    def get_sub_entity_info(self, sub_id: str) -> dict[str, Any] | None:
        """获取子实体的信息（皮肤或地图信息）

        :param sub_id: 子实体ID（皮肤ID或地图ID）
        :returns: 包含id和name的字典，不存在时返回None
        """
        sub_entity = self.sub_entities.get(sub_id)
        if not sub_entity:
            return None

        return {"id": int(sub_id), "name": sub_entity["name"]}

    def get_wad_path(self, audio_type: str) -> Path | None:
        """根据音频类型获取对应的WAD文件完整路径

        :param audio_type: 音频类型（"VO"需要语言WAD，其他使用根WAD）
        :returns: 存在的WAD文件完整路径，不存在时返回None
        """
        # 获取相对路径
        if audio_type == "VO":
            relative_path = self.wad_language
        else:
            relative_path = self.wad_root

        # 如果没有相对路径，直接返回None
        if not relative_path:
            return None

        # 构建完整路径并检查存在性
        full_path = config.GAME_PATH / relative_path
        return full_path if full_path.exists() else None

    @classmethod
    def from_champion(cls, champion_id: int, reader) -> "AudioEntityData":
        """从英雄数据创建AudioEntityData实例

        :param champion_id: 英雄ID
        :param reader: 数据读取器实例
        :returns: AudioEntityData实例
        :raises ValueError: 当英雄数据不存在或无音频数据时
        """
        # 获取英雄基础信息
        champion = reader.get_champion(champion_id)
        if not champion:
            raise ValueError(f"数据中不存在英雄ID {champion_id}")

        # 获取英雄音频合集数据
        champion_banks = reader.get_champion_banks(champion_id)
        if not champion_banks:
            raise ValueError(f"英雄ID {champion_id} 没有音频数据")

        # 获取WAD文件信息
        wad_info = champion.get("wad", {})
        wad_root = wad_info.get("root")
        if not wad_root:
            raise ValueError(f"英雄ID {champion_id} 缺少根WAD文件信息")

        # 获取语言设置
        language = config.GAME_REGION
        wad_language = wad_info.get(language)  # 可能为None，某些英雄可能没有语言WAD

        # 创建皮肤ID到皮肤信息的映射
        skin_info_map = {}
        for skin in champion.get("skins", []):
            skin_id = skin.get("id")
            skin_id_str = str(skin_id)
            skin_name_raw = skin.get("skinNames", {}).get(language, skin.get("skinNames", {}).get("default", ""))
            is_base_skin = skin.get("isBase", False)
            skin_name = "基础皮肤" if is_base_skin else skin_name_raw
            # 安全化皮肤名称，确保文件系统兼容性
            safe_skin_name = sanitize_filename(skin_name)
            skin_info_map[skin_id_str] = {"id": skin_id, "name": safe_skin_name}

        # 构建子实体数据
        sub_entities = {}
        available_skins = champion_banks.get("skins", {})

        for skin_id_str, banks in available_skins.items():
            skin_info = skin_info_map.get(skin_id_str)
            if not skin_info:
                continue

            sub_entities[skin_id_str] = {"name": skin_info["name"], "categories": banks}

        # 安全化英雄名称
        champion_name_raw = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))
        safe_champion_name = sanitize_filename(champion_name_raw)
        safe_champion_alias = sanitize_filename(champion.get("alias", "").lower())

        return cls(
            entity_id=str(champion_id),
            entity_name=safe_champion_name,
            entity_alias=safe_champion_alias,
            entity_type="champion",
            sub_entities=sub_entities,
            wad_root=wad_root,
            wad_language=wad_language,
        )

    @classmethod
    def from_map(cls, map_id: int, reader) -> "AudioEntityData":
        """从地图数据创建AudioEntityData实例

        :param map_id: 地图ID
        :param reader: 数据读取器实例
        :returns: AudioEntityData实例
        :raises ValueError: 当地图数据不存在或无音频数据时
        """
        # 获取地图基础信息
        map_info = reader.get_map(map_id)
        if not map_info:
            raise ValueError(f"数据中不存在地图ID {map_id}")

        # 获取地图音频合集数据
        map_banks = reader.get_map_banks(map_id)
        if not map_banks:
            raise ValueError(f"地图ID {map_id} 没有音频数据")

        # 获取WAD文件信息
        wad_info = map_info.get("wad", {})
        wad_root = wad_info.get("root")
        if not wad_root:
            raise ValueError(f"地图ID {map_id} 缺少根WAD文件信息")

        # 获取语言设置
        language = config.GAME_REGION
        wad_language = wad_info.get(language)  # 可能为None，某些地图可能没有语言WAD

        # 获取地图名称（支持本地化）
        map_name_raw = map_info.get("names", {}).get(language, map_info.get("names", {}).get("default", ""))
        safe_map_name = sanitize_filename(map_name_raw)

        # 获取地图别名
        map_alias_raw = "common" if map_id == 0 else map_info.get("mapStringId", "").lower()
        safe_map_alias = sanitize_filename(map_alias_raw)

        # 地图作为自己的唯一"子实体"
        sub_entities = {str(map_id): {"name": safe_map_name, "categories": map_banks.get("banks", {})}}

        return cls(
            entity_id=str(map_id),
            entity_name=safe_map_name,
            entity_alias=safe_map_alias,
            entity_type="map",
            sub_entities=sub_entities,
            wad_root=wad_root,
            wad_language=wad_language,
        )


def unpack_audio_entity(entity_data: AudioEntityData, reader: DataReader) -> None:
    """通用音频解包函数，支持英雄和地图数据

    :param entity_data: 音频实体数据（英雄或地图）
    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :raises ValueError: 当实体数据无效时
    """
    language = config.GAME_REGION  # 决定解包哪种语言的音频
    logger.info(f"开始解包{entity_data.entity_type}ID {entity_data.entity_id} 的音频文件，语言: {language}")

    # 从配置中读取要排除的音频类型，去除空白并转大写统一格式
    excluded_types = {t.strip().upper() for t in config.EXCLUDE_TYPE if t.strip()}
    logger.info(
        f"将要解包的音频类型 (已排除: {excluded_types if excluded_types else '无'}): "
        f"{[t for t in [reader.AUDIO_TYPE_VO, reader.AUDIO_TYPE_SFX, reader.AUDIO_TYPE_MUSIC] if t not in excluded_types]}"
    )

    logger.info(
        f"{entity_data.entity_type}信息: ID={entity_data.entity_id}, 别名={entity_data.entity_alias}, 名称={entity_data.entity_name}"
    )

    # --- 阶段 1: 收集所有需要解包的音频文件路径 ---
    logger.info("阶段 1: 收集所有需要解包的音频文件路径...")

    # VO（语音）文件通常存储在特定语言的WAD文件中
    vo_paths_to_extract = set()
    vo_path_to_sub_info_map = {}
    # SFX（音效）和Music（音乐）文件通常存储在根WAD文件中
    other_paths_to_extract = set()
    other_path_to_sub_info_map = {}

    # 直接遍历实体的所有子实体（皮肤或地图）
    for sub_id, sub_data in entity_data.sub_entities.items():
        sub_info = entity_data.get_sub_entity_info(sub_id)
        if not sub_info:
            logger.warning(f"子实体ID {sub_id} 信息不完整，跳过处理")
            continue

        sub_name = sub_info["name"]
        sub_id_int = sub_info["id"]

        # 遍历该子实体的所有音频类别（如VO、SFX等）
        for category, banks_list in sub_data["categories"].items():
            # 通过类别名称判断音频类型（VO/SFX/MUSIC）
            audio_type = reader.get_audio_type(category)

            if audio_type in excluded_types:
                continue

            # 创建包含子实体信息和音频类型的字典，用于后续文件组织
            sub_info_with_type = {"id": sub_id_int, "name": sub_name, "type": audio_type}

            # 根据音频类型分别处理，VO文件和其他类型文件存储在不同WAD中
            if audio_type == reader.AUDIO_TYPE_VO:
                for bank in banks_list:  # banks_list是合集列表
                    for path in bank:  # 每个合集包含多个文件路径
                        vo_paths_to_extract.add(path)
                        vo_path_to_sub_info_map[path] = sub_info_with_type
            else:  # SFX 和 MUSIC
                for bank in banks_list:  # banks_list是合集列表
                    for path in bank:  # 每个合集包含多个文件路径
                        other_paths_to_extract.add(path)
                        other_path_to_sub_info_map[path] = sub_info_with_type

    # 检查是否收集到了任何需要处理的音频文件
    if not vo_paths_to_extract and not other_paths_to_extract:
        logger.warning(
            f"{entity_data.entity_type} '{entity_data.entity_name}' 未找到任何需要解包的音频文件 (检查排除类型配置)。"
        )
        return

    # --- 阶段 2: 根据不同WAD文件，批量解包 ---
    logger.info("阶段 2: 开始批量解包WAD文件...")
    path_to_raw_data_map = {}

    # 2.1 从特定语言的WAD文件中解包VO（语音）文件
    lang_wad_path = entity_data.get_wad_path("VO")
    if lang_wad_path and vo_paths_to_extract:
        vo_path_list = list(vo_paths_to_extract)  # 无需排序（WAD.extract保证顺序）
        try:
            logger.info(f"正在从 {lang_wad_path.name} 解包 {len(vo_path_list)} 个VO文件...")
            file_raws = WAD(lang_wad_path).extract(vo_path_list, raw=True)
            path_to_raw_data_map.update(zip(vo_path_list, file_raws, strict=False))
        except Exception as e:
            logger.error(f"解包语言WAD文件 '{lang_wad_path.name}' 时出错: {e}")
            logger.debug(traceback.format_exc())
    elif vo_paths_to_extract:
        logger.warning("语言WAD文件不存在，跳过VO解包。")

    # 2.2 从根WAD文件中解包SFX（音效）和Music（音乐）文件
    root_wad_path = entity_data.get_wad_path("SFX")
    if root_wad_path and other_paths_to_extract:
        other_path_list = list(other_paths_to_extract)  # 无需排序（WAD.extract保证顺序）
        try:
            logger.info(f"正在从 {root_wad_path.name} 解包 {len(other_path_list)} 个SFX/Music文件...")
            file_raws = WAD(root_wad_path).extract(other_path_list, raw=True)
            path_to_raw_data_map.update(zip(other_path_list, file_raws, strict=False))
        except Exception as e:
            logger.error(f"解包根WAD文件 '{root_wad_path.name}' 时出错: {e}")
            logger.debug(traceback.format_exc())
    elif other_paths_to_extract:
        logger.warning("根WAD文件不存在，跳过SFX/Music解包。")

    # --- 阶段 3: 组装最终数据 ---
    logger.info("阶段 3: 组装并处理最终数据...")
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

    logger.success(f"所有子实体的音频文件解包完成，共 {len(unpacked_audio_data)} 个子实体。开始处理解包后的文件...")

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
            output_path = generate_output_path(entity_data, sub_id_str, audio_type)
            output_path.mkdir(parents=True, exist_ok=True)
            wad_file_used = entity_data.get_wad_path(audio_type)
            wad_file_name = wad_file_used.name if wad_file_used else "无WAD文件"

            logger.info(
                f"正在处理子实体 '{sub_name}' (ID: {sub_id}, 类型: {audio_type}) | "
                f"实体: {entity_data.entity_type} '{entity_data.entity_name}' (ID: {entity_data.entity_id}) | "
                f"WAD: {wad_file_name} | 工作目录: {output_path}"
            )

            # 初始化统计计数器
            success_count, container_skipped_count, subfile_skipped_count, error_count = 0, 0, 0, 0
            empty_containers = []  # 收集空容器的路径信息用于调试
            failed_files = []  # 收集处理失败的文件信息
            for file_info in files_in_type:
                file_size = len(file_info["raw"]) if file_info["raw"] else 0

                logger.debug(f"  - 类型: {file_info['suffix']}, 大小: {file_size} 字节")

                if file_size == 0:
                    container_skipped_count += 1
                    # 记录空容器的来源信息
                    source_path = file_info.get("source_path", "未知路径")
                    empty_containers.append(source_path)
                    continue

                if file_info["suffix"] == ".bnk":
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
                        source_path = file_info.get("source_path", "未知路径")
                        logger.warning(f"处理BNK文件失败: {e} | 文件路径: {source_path}")
                        failed_files.append({"path": source_path, "error": str(e), "type": "BNK"})
                        error_count += 1
                elif file_info["suffix"] == ".wpk":
                    try:
                        wpk = WPK(file_info["raw"])
                        for file in wpk.extract_files():
                            file.save_file(output_path / f"{file.filename}")
                            logger.trace(f"WPK, 已解包 {file.filename} 文件")
                            success_count += 1
                    except Exception as e:
                        source_path = file_info.get("source_path", "未知路径")
                        logger.warning(f"处理WPK文件失败: {e} | 文件路径: {source_path}")
                        failed_files.append({"path": source_path, "error": str(e), "type": "WPK"})
                        error_count += 1
                else:
                    # 如果遇到未知的文件类型，记录警告和文件路径
                    source_path = file_info.get("source_path", "未知路径")
                    logger.warning(f"未知的文件类型: {file_info['suffix']} | 文件路径: {source_path}")
                    failed_files.append(
                        {"path": source_path, "error": f"未知文件类型: {file_info['suffix']}", "type": "UNKNOWN"}
                    )
                    error_count += 1

            # 构建处理结果的汇总消息
            summary_message = (
                f"子实体 '{sub_name}' (ID: {sub_id}, 类型: {audio_type}) 处理完成 | "
                f"实体: {entity_data.entity_type} '{entity_data.entity_name}' (ID: {entity_data.entity_id}) | "
                f"WAD: {wad_file_name} | 结果: 成功 {success_count} 个"
            )

            # 收集需要报告的详细信息
            details = []

            if subfile_skipped_count > 0:
                details.append(f"跳过空子文件 {subfile_skipped_count} 个")

            if container_skipped_count > 0:
                details.append(f"跳过空容器 {container_skipped_count} 个")
                if empty_containers:
                    logger.debug(f"空容器路径: {empty_containers}")

            if error_count > 0:
                details.append(f"处理失败 {error_count} 个")
                if failed_files:
                    logger.debug("失败文件详情:")
                    for failed_file in failed_files:
                        logger.debug(
                            f"  - 类型: {failed_file['type']}, 错误: {failed_file['error']}, 路径: {failed_file['path']}"
                        )

            # 如果有详细信息，将其添加到汇总消息中
            if details:
                summary_message += f" ({', '.join(details)})"
            summary_message += "."

            # 根据是否有错误或跳过的容器来决定日志级别
            if error_count > 0 or container_skipped_count > 0:
                # 如果有错误或跳过的容器，使用警告级别
                logger.warning(summary_message)
            else:
                # 如果处理完全成功，使用成功级别
                logger.success(summary_message)


def _generate_relative_path(entity_data: AudioEntityData, sub_id: str) -> str:
    """生成相对路径（不包含音频类型）

    :param entity_data: 实体数据
    :param sub_id: 子实体ID（皮肤ID或地图ID）
    :returns: 相对路径字符串
    """
    sub_name = entity_data.sub_entities[sub_id]["name"]

    if entity_data.entity_type == "champion":
        # Champions\10·kayle·正义天使\10000·基础皮肤
        return f"Champions\\{entity_data.entity_id}·{entity_data.entity_alias}·{entity_data.entity_name}\\{sub_id}·{sub_name}"
    else:  # map
        # Maps\11·sr·召唤师峡谷
        return f"Maps\\{entity_data.entity_id}·{entity_data.entity_alias}·{entity_data.entity_name}"


def generate_output_path(
    entity_data: AudioEntityData, sub_id: str, audio_type: str, base_path: Path | None = None
) -> Path:
    """生成完整的输出路径

    根据 config.GROUP_BY_TYPE 配置决定目录结构：
    - True: audios/VO/Champions/10·kayle·正义天使/10000·基础皮肤
    - False: audios/Champions/10·kayle·正义天使/10000·基础皮肤/VO

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


def unpack_champion(champion_id: int, reader: DataReader) -> None:
    """根据英雄ID和已加载的数据读取器解包其音频文件

    :param champion_id: 英雄ID
    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :raises ValueError: 当英雄数据不存在或无音频数据时
    """
    try:
        # 创建AudioEntityData实例
        entity_data = AudioEntityData.from_champion(champion_id, reader)
        # 调用通用解包函数
        unpack_audio_entity(entity_data, reader)
    except ValueError as e:
        # 保持与原始函数相同的错误处理方式
        logger.error(str(e))
        return


def unpack_map_audio(map_id: int, reader: DataReader) -> None:
    """根据地图ID和已加载的数据读取器解包其音频文件

    :param map_id: 地图ID
    :param reader: 一个已经初始化并加载了数据的DataReader实例
    :raises ValueError: 当地图数据不存在或无音频数据时
    """
    try:
        # 创建AudioEntityData实例
        entity_data = AudioEntityData.from_map(map_id, reader)
        # 调用通用解包函数
        unpack_audio_entity(entity_data, reader)
    except ValueError as e:
        # 保持一致的错误处理方式
        logger.error(str(e))
        return


def generate_champion_tasks(reader: DataReader, champion_ids: list[int] | None = None) -> list[tuple[str, int, str]]:
    """生成英雄解包任务集

    :param reader: 数据读取器
    :param champion_ids: 指定的英雄ID列表，None表示所有英雄
    :returns: 任务元组列表 [("champion", id, description), ...]
    :raises ValueError: 当指定的ID不存在时
    """
    champions = reader.get_champions()
    available_ids = {champ.get("id") for champ in champions if champ.get("id") is not None}

    if champion_ids is None:
        # 处理所有英雄
        return [
            ("champion", champ.get("id"), f"英雄ID {champ.get('id')}")
            for champ in champions
            if champ.get("id") is not None
        ]
    else:
        # 验证指定的ID
        invalid_ids = [cid for cid in champion_ids if cid not in available_ids]
        if invalid_ids:
            raise ValueError(f"无效的英雄ID: {invalid_ids}")

        # 生成指定ID的任务
        return [("champion", cid, f"英雄ID {cid}") for cid in champion_ids]


def generate_map_tasks(reader: DataReader, map_ids: list[int] | None = None) -> list[tuple[str, int, str]]:
    """生成地图解包任务集

    :param reader: 数据读取器
    :param map_ids: 指定的地图ID列表，None表示所有地图
    :returns: 任务元组列表 [("map", id, description), ...]
    :raises ValueError: 当指定的ID不存在时
    """
    maps = reader.get_maps()
    available_ids = {map_data.get("id") for map_data in maps if map_data.get("id") is not None}

    if map_ids is None:
        # 处理所有地图
        return [
            ("map", map_data.get("id"), f"地图ID {map_data.get('id')}")
            for map_data in maps
            if map_data.get("id") is not None
        ]
    else:
        # 验证指定的ID
        invalid_ids = [mid for mid in map_ids if mid not in available_ids]
        if invalid_ids:
            raise ValueError(f"无效的地图ID: {invalid_ids}")

        # 生成指定ID的任务
        return [("map", mid, f"地图ID {mid}") for mid in map_ids]


def execute_unpack_tasks(tasks: list[tuple[str, int, str]], reader: DataReader, max_workers: int = 4) -> None:
    """执行解包任务集

    :param tasks: 任务元组列表 [("entity_type", id, description), ...]
    :param reader: 数据读取器
    :param max_workers: 最大工作线程数
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

    def unpack_entity(entity_type: str, entity_id: int) -> None:
        """解包单个实体的辅助函数"""
        if entity_type == "champion":
            unpack_champion(entity_id, reader)
        elif entity_type == "map":
            unpack_map_audio(entity_id, reader)
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
    logger.success(f"全部 {' 和 '.join(summary_parts)} 解包完成，总耗时: {end_time - start_time:.2f} 秒。")

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
        logger.info(f"已添加 {len(champion_tasks)} 个英雄解包任务")

    # 生成地图任务
    if include_maps:
        map_tasks = generate_map_tasks(reader, None)
        tasks.extend(map_tasks)
        logger.info(f"已添加 {len(map_tasks)} 个地图解包任务")

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
