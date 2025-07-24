# 🐍 Explicit is better than implicit.
# 🐼 明了优于隐晦
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/5/6 1:19
# @Update  : 2025/7/25 2:51
# @Detail  : 游戏数据管理器


import json
import re
import shutil
import tempfile
import traceback
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any

from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.Utils.common import Singleton, dump_json, format_region, load_json
from lol_audio_unpack.Utils.config import config
from lol_audio_unpack.Utils.type_hints import StrPath

# 类型别名定义
ChampionData = dict[str, Any]
SkinData = dict[str, Any]
AudioData = dict[str, list[str]]
BinMapping = dict[str, dict[str, Any]]


class ProgressTracker:
    """
    进度跟踪器，用于记录和显示处理进度
    """

    def __init__(self, total: int, description: str, log_interval: int = 10):
        """
        初始化进度跟踪器

        :param total: 总项目数
        :param description: 进度描述
        :param log_interval: 日志记录间隔
        """
        self.total = total
        self.current = 0
        self.description = description
        self.log_interval = log_interval
        self.start_time = datetime.now()
        logger.info(f"开始{description}，总计 {total} 项")

    def update(self, increment: int = 1) -> None:
        """
        更新进度

        :param increment: 增量，默认为1
        """
        self.current += increment
        if self.current % self.log_interval == 0 or self.current == self.total:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            percentage = (self.current / self.total) * 100
            logger.info(
                f"{self.description}进度: {self.current}/{self.total} ({percentage:.1f}%)，已用时 {elapsed:.1f}秒"
            )

    def finish(self) -> None:
        """
        完成进度跟踪，显示最终结果
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        logger.success(f"{self.description}完成，共 {self.current}/{self.total} 项，用时 {elapsed:.1f}秒")


class DataUpdater:
    """
    负责游戏数据的更新和多语言JSON合并
    """

    # 音频类型常量定义
    AUDIO_TYPE_SFX = "SFX"  # 音效
    AUDIO_TYPE_VO = "VO"  # 语音
    AUDIO_TYPE_SFX_OUTOFGAME = "SFX_OutOfGame"  # 游戏外音效(如大厅、选择英雄时)
    AUDIO_TYPE_VO_OUTOFGAME = "VO_OutOfGame"  # 游戏外语音
    AUDIO_TYPE_REWORK_SFX = "Rework_SFX"  # Skarner重做的特殊音效类型

    # 已知的音频类型集合，用于验证
    KNOWN_AUDIO_TYPES = {
        AUDIO_TYPE_SFX,
        AUDIO_TYPE_VO,
        AUDIO_TYPE_SFX_OUTOFGAME,
        AUDIO_TYPE_VO_OUTOFGAME,
        AUDIO_TYPE_REWORK_SFX,
    }

    def __init__(self, languages: list[str] | None = None) -> None:
        """
        初始化数据更新器

        :param languages: 需要处理的语言列表（不包括default，default会自动添加）。
                        如果为None，则使用config中的GAME_REGION。
        """
        # 从配置中获取游戏根目录
        self.game_path: Path = config.GAME_PATH
        # 从配置中获取数据清单输出目录
        self.manifest_path: Path = config.MANIFEST_PATH
        # 临时工作目录，用于存放解包过程中的临时文件
        self.temp_path: Path = config.TEMP_PATH

        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        # 处理语言列表
        if languages is None:
            # 从config获取，如果没有则使用默认值
            game_region = config.GAME_REGION or "zh_CN"
            # 需要处理的目标语言列表
            self.languages: list[str] = [game_region]
        else:
            self.languages: list[str] = languages

        # 当前游戏版本，如 "14.14"
        self.version: str = self._get_game_version()
        # 特定版本的数据清单文件目录
        self.version_manifest_path: Path = self.manifest_path / self.version
        # 最终合并的数据文件路径
        self.merged_file: Path = self.version_manifest_path / "merged_data.json"
        # 实际处理的语言列表，包含 "default"
        self.process_languages: list[str] = self._prepare_language_list(self.languages)

        # 确保版本清单目录存在
        self.version_manifest_path.mkdir(parents=True, exist_ok=True)

    def _extract_audio_type(self, category: str) -> str:
        """
        从分类字符串中提取音频类型标识

        :param category: 原始分类字符串(如'Aatrox_Base_SFX'或'Draven_Base_SFX_OutOfGame')
        :return: 音频类型标识(如'SFX'或'SFX_OutOfGame')
        """
        parts = category.split("_")
        if len(parts) < 3:
            logger.warning(f"异常的音频分类格式: {category}")
            return "unknown"

        # 特殊情况处理: Skarner重做, 实际上和SFX内容是一样的，先保留代码，万一呢？
        if parts[0] == "Skarner" and parts[1] == "Rework" and len(parts) >= 4:
            logger.debug(f"检测到特殊的Skarner重做分类: {category}")
            return self.AUDIO_TYPE_REWORK_SFX  # 返回特殊类型标识

        # 通常格式为 [英雄名]_[皮肤]_[类型] 或 [英雄名]_[皮肤]_[类型]_[子类型]
        # 先尝试判断是否为已知的复合类型
        if len(parts) >= 4:
            potential_compound_type = "_".join(parts[2:])  # 合并第三个部分之后的所有部分
            if potential_compound_type in self.KNOWN_AUDIO_TYPES:
                return potential_compound_type

        # 如果不是复合类型，则返回第三个部分
        _type = parts[2]

        # 检查是否为已知类型，如果不是，记录警告
        if _type not in self.KNOWN_AUDIO_TYPES:
            logger.warning(f"发现未知的音频类型: {_type}，来自分类: {category}，可能需要额外处理")

        return _type

    def check_and_update(self) -> Path:
        """
        检查游戏版本并更新数据

        :return: 合并后的数据文件路径
        """
        # 检查是否需要更新
        if not self._needs_update():
            return self.merged_file

        # 使用config中的TEMP_PATH创建本次运行的临时目录
        # 通过添加时间戳确保每次运行的目录唯一
        run_temp_path = self.temp_path / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_temp_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建临时目录用于解包: {run_temp_path}")

        try:
            # 提取和处理数据
            self._process_data(run_temp_path)
            logger.success(f"数据更新完成: {self.merged_file}")
            return self.merged_file
        finally:
            # 根据是否为开发模式决定是否删除临时目录
            if not config.is_dev_mode():
                try:
                    shutil.rmtree(run_temp_path)
                    logger.info(f"已清理临时目录: {run_temp_path}")
                except OSError as e:
                    logger.error(f"清理临时目录失败: {run_temp_path}, error: {e}")
            else:
                logger.warning(f"开发模式，临时目录未删除: {run_temp_path}")

    def _prepare_language_list(self, languages: list[str]) -> list[str]:
        """
        准备处理语言列表，确保default在列表中

        :param languages: 输入的语言列表
        :return: 处理后的语言列表
        """
        process_languages = ["default"]
        for lang in languages:
            if lang.lower() not in ["default", "en_us"]:
                process_languages.append(lang)
        return process_languages

    def _needs_update(self) -> bool:
        """
        检查是否需要更新数据

        :return: 是否需要更新
        """
        if not self.merged_file.exists():
            return True

        try:
            with open(self.merged_file, encoding="utf-8") as f:
                existing_data = json.load(f)

            # 检查现有文件包含的语言
            existing_languages = set(existing_data.get("languages", []))
            existing_languages.add("default")  # default总是包含的

            # 检查请求的所有语言是否都已包含
            requested_languages = set(self.process_languages)

            # 如果所有请求的语言都已包含在现有文件中，则不需要更新
            if requested_languages.issubset(existing_languages):
                logger.info(f"数据文件已是最新版本: {self.version}，且包含所有请求的语言")
                return False
            else:
                missing_langs = requested_languages - existing_languages
                logger.info(f"需要更新数据文件，缺少语言: {missing_langs}")
                return True
        except Exception as e:
            logger.error(f"检查现有数据文件时出错: {str(e)}")
            # 出错时默认需要更新
            return True

    def _process_data(self, temp_path: Path) -> None:
        """
        处理游戏数据，包括提取、合并和验证

        :param temp_path: 临时路径
        """
        # 创建进度跟踪器
        progress = ProgressTracker(len(self.process_languages), "语言数据提取", log_interval=1)

        # 提取需要的数据
        for language in self.process_languages:
            logger.info(f"正在处理 {language} 语言数据...")
            self._extract_wad_data(temp_path, language)
            progress.update()
        progress.finish()

        # 合并多语言数据
        logger.info("合并多语言数据...")
        self._merge_language_data(temp_path)

        # 验证WAD文件是否存在并更新路径信息
        logger.info("验证WAD文件路径...")
        self._verify_wad_paths(temp_path)

        # 处理BIN文件，提取音频路径
        logger.info("处理BIN文件，提取音频路径...")
        self._process_bin_files(temp_path)

        # 将合并后的数据文件复制到输出目录
        temp_merged_file = temp_path / self.version / "merged_data.json"
        if temp_merged_file.exists():
            self.version_manifest_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_merged_file, self.merged_file)
            logger.info(f"已复制合并数据到: {self.merged_file}")
        else:
            raise FileNotFoundError(f"未能创建合并数据文件: {temp_merged_file}")

    def _process_bin_files(self, temp_path: Path) -> None:
        """
        处理BIN文件，提取音频路径并添加到皮肤数据中

        :param temp_path: 临时目录路径
        """
        merged_file = temp_path / self.version / "merged_data.json"

        if not merged_file.exists():
            logger.error(f"合并数据文件不存在: {merged_file}")
            return

        try:
            # 使用common.py中的load_json函数
            data = load_json(merged_file)
            if not data:
                logger.error(f"无法加载合并数据文件: {merged_file}")
                return

            # 获取英雄总数并创建进度跟踪器
            champions = data.get("champions", {})
            champion_count = len(champions)
            progress = ProgressTracker(champion_count, "英雄音频数据处理", log_interval=5)

            # 遍历所有英雄
            for champion_id, champion_data in champions.items():
                self._extract_champion_audio(champion_data, champion_id)
                progress.update()

            progress.finish()

            # 使用common.py中的dump_json函数保存更新后的数据
            dump_json(data, merged_file)

        except Exception as e:
            logger.error(f"处理BIN文件时出错: {str(e)}")
            logger.debug(traceback.format_exc())

    def _extract_champion_audio(self, champion_data: ChampionData, champion_id: str) -> None:
        """
        提取单个英雄的音频数据

        :param champion_data: 英雄数据
        :param champion_id: 英雄ID
        """
        if "wad" not in champion_data or "skins" not in champion_data:
            return

        alias = champion_data.get("alias", "").lower()
        if not alias:
            return

        # 获取基础WAD路径
        root_wad_path = champion_data["wad"].get("root")
        if not root_wad_path:
            return

        full_wad_path = self.game_path / root_wad_path
        if not full_wad_path.exists():
            logger.error(f"英雄 {alias} 的WAD文件不存在: {full_wad_path}")
            return

        # 构造所有皮肤和炫彩的BIN文件路径和映射
        bin_paths, bin_mapping = self._build_bin_path_mapping(champion_data, champion_id, alias)

        if not bin_paths:
            return

        # 记录映射示例用于调试
        if bin_mapping:
            sample_mapping = dict(list(bin_mapping.items())[:2])
            logger.debug(f"BIN路径映射示例: {sample_mapping}")

        # 从WAD中提取BIN文件
        logger.debug(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")

        try:
            # 提取BIN文件
            bin_raws = WAD(full_wad_path).extract(bin_paths, raw=True)
            self._process_bin_raw_data(bin_raws, bin_paths, bin_mapping, champion_data)

        except Exception as e:
            logger.error(f"处理英雄 {alias} 的BIN文件时出错: {str(e)}")
            logger.debug(traceback.format_exc())

    def _build_bin_path_mapping(
        self, champion_data: ChampionData, champion_id: str, alias: str
    ) -> tuple[list[str], BinMapping]:
        """
        构建BIN文件路径和数据映射关系

        :param champion_data: 英雄数据
        :param champion_id: 英雄ID
        :param alias: 英雄别名
        :return: BIN路径列表和映射字典
        """
        bin_paths = []
        bin_mapping = {}

        # 处理普通皮肤，确保基础皮肤(skin0)在最前面
        base_skin_index = None

        # 第一遍查找基础皮肤索引
        for i, skin in enumerate(champion_data.get("skins", [])):
            if skin.get("isBase", False):
                base_skin_index = i
                break

        # 如果找到基础皮肤，先处理它
        if base_skin_index is not None:
            self._process_skin_bin_path(champion_data, champion_id, alias, base_skin_index, bin_paths, bin_mapping)

        # 处理其他所有皮肤
        for i, skin in enumerate(champion_data.get("skins", [])):
            if i == base_skin_index:  # 跳过已处理的基础皮肤
                continue

            # 处理普通皮肤
            self._process_skin_bin_path(champion_data, champion_id, alias, i, bin_paths, bin_mapping)

            # 处理该皮肤的所有炫彩
            for j, chroma in enumerate(skin.get("chromas", [])):
                self._process_chroma_bin_path(champion_data, champion_id, alias, i, j, bin_paths, bin_mapping)

        return bin_paths, bin_mapping

    def _process_skin_bin_path(
        self,
        champion_data: ChampionData,
        champion_id: str,
        alias: str,
        skin_index: int,
        bin_paths: list[str],
        bin_mapping: BinMapping,
    ) -> None:
        """
        处理单个皮肤的BIN文件路径

        :param champion_data: 英雄数据
        :param champion_id: 英雄ID
        :param alias: 英雄别名
        :param skin_index: 皮肤索引
        :param bin_paths: BIN路径列表，将会被修改
        :param bin_mapping: BIN路径映射，将会被修改
        """
        skin = champion_data["skins"][skin_index]
        skin_id = self._parse_skin_id(skin.get("id"), int(champion_id))
        bin_path = f"data/characters/{alias}/skins/skin{skin_id}.bin"
        # 保存BIN文件路径到皮肤数据中
        champion_data["skins"][skin_index]["binPath"] = bin_path
        bin_paths.append(bin_path)
        bin_mapping[bin_path] = {"type": "skin", "index": skin_index}

    def _process_chroma_bin_path(
        self,
        champion_data: ChampionData,
        champion_id: str,
        alias: str,
        skin_index: int,
        chroma_index: int,
        bin_paths: list[str],
        bin_mapping: BinMapping,
    ) -> None:
        """
        处理单个炫彩皮肤的BIN文件路径

        :param champion_data: 英雄数据
        :param champion_id: 英雄ID
        :param alias: 英雄别名
        :param skin_index: 皮肤索引
        :param chroma_index: 炫彩索引
        :param bin_paths: BIN路径列表，将会被修改
        :param bin_mapping: BIN路径映射，将会被修改
        """
        chroma = champion_data["skins"][skin_index]["chromas"][chroma_index]
        chroma_id = self._parse_skin_id(chroma.get("id"), int(champion_id))
        chroma_bin_path = f"data/characters/{alias}/skins/skin{chroma_id}.bin"
        # 保存BIN文件路径到炫彩皮肤数据中
        champion_data["skins"][skin_index]["chromas"][chroma_index]["binPath"] = chroma_bin_path
        bin_paths.append(chroma_bin_path)
        bin_mapping[chroma_bin_path] = {"type": "chroma", "skin_index": skin_index, "chroma_index": chroma_index}

    def _process_bin_raw_data(
        self,
        bin_raws: list[bytes],
        bin_paths: list[str],
        bin_mapping: BinMapping,
        champion_data: ChampionData,
    ) -> None:
        """
        处理BIN文件原始数据并更新英雄数据

        :param bin_raws: BIN文件原始数据列表
        :param bin_paths: BIN文件路径列表
        :param bin_mapping: BIN路径到数据映射
        :param champion_data: 英雄数据
        """
        # 首先提取基础皮肤的数据，用于后续去重
        base_categories = self._process_base_skin_bin(bin_raws, bin_paths, bin_mapping, champion_data)

        # 处理其他皮肤数据
        self._process_other_skins_bin(bin_raws, bin_paths, bin_mapping, champion_data, base_categories)

    def _iterate_bin_banks(self, bin_file: BIN) -> "Generator[tuple[str, str, list[str]]]":
        """
        遍历BIN文件中的所有bank，并根据bank_path进行去重。

        :param bin_file: BIN文件对象
        :yield: (类型, 分类, bank路径)
        """
        processed_bank_paths: set[tuple] = set()
        for entry in bin_file.data:
            for bank in entry.bank_units:
                if not bank.bank_path:
                    continue

                bank_path_tuple = tuple(bank.bank_path)
                if bank_path_tuple in processed_bank_paths:
                    continue
                processed_bank_paths.add(bank_path_tuple)

                _type = self._extract_audio_type(bank.category)
                yield _type, bank.category, bank.bank_path

    def _process_base_skin_bin(
        self,
        bin_raws: list[bytes],
        bin_paths: list[str],
        bin_mapping: BinMapping,
        champion_data: ChampionData,
    ) -> dict[str, list[str]]:
        """
        处理基础皮肤的BIN文件

        :param bin_raws: BIN文件原始数据列表
        :param bin_paths: BIN文件路径列表
        :param bin_mapping: BIN路径到数据映射
        :param champion_data: 英雄数据
        :return: 基础皮肤的音频分类信息，用于后续去重
        """
        base_categories = {}
        base_skin_path = None
        base_skin_index = None

        # 查找基础皮肤的BIN路径和索引
        for path, info in bin_mapping.items():
            if info["type"] == "skin":
                skin_index = info["index"]
                if champion_data["skins"][skin_index].get("isBase", False):
                    base_skin_path = path
                    base_skin_index = skin_index
                    break

        # 如果找到基础皮肤路径，先处理它的数据
        if base_skin_path and base_skin_index is not None:
            base_path_index = bin_paths.index(base_skin_path)
            if base_path_index < len(bin_raws) and bin_raws[base_path_index]:
                try:
                    bin_file = BIN(bin_raws[base_path_index])
                    # 处理主题音乐
                    if bin_file.theme_music:
                        logger.info(f"发现英雄主题音乐 数量: {len(bin_file.theme_music)}")
                        # 暂不做任何处理
                        # if "themeMusic" not in champion_data:
                        #     champion_data["themeMusic"] = bin_file.theme_music

                    for _type, category, bank_path in self._iterate_bin_banks(bin_file):
                        if _type not in base_categories:
                            base_categories[_type] = []
                        base_categories[_type].append(category)

                        # 初始化基础皮肤的audioData结构
                        if "audioData" not in champion_data["skins"][base_skin_index]:
                            champion_data["skins"][base_skin_index]["audioData"] = {}

                        # 为基础皮肤添加音频数据
                        if _type not in champion_data["skins"][base_skin_index]["audioData"]:
                            champion_data["skins"][base_skin_index]["audioData"][_type] = []

                        champion_data["skins"][base_skin_index]["audioData"][_type].append(bank_path)

                except Exception as e:
                    logger.error(f"解析基础皮肤BIN文件失败: {base_skin_path}, 错误: {e}")
                    logger.debug(traceback.format_exc())

        return base_categories

    def _process_other_skins_bin(
        self,
        bin_raws: list[bytes],
        bin_paths: list[str],
        bin_mapping: BinMapping,
        champion_data: ChampionData,
        base_categories: dict[str, list[str]],
    ) -> None:
        """
        处理非基础皮肤的BIN文件

        :param bin_raws: BIN文件原始数据列表
        :param bin_paths: BIN文件路径列表
        :param bin_mapping: BIN路径到数据映射
        :param champion_data: 英雄数据
        :param base_categories: 基础皮肤的音频分类信息，用于去重
        """
        # 查找基础皮肤路径
        base_skin_path = None
        for path, info in bin_mapping.items():
            if info["type"] == "skin" and champion_data["skins"][info["index"]].get("isBase", False):
                base_skin_path = path
                break

        # 处理所有皮肤数据
        for i, bin_path in enumerate(bin_paths):
            if i >= len(bin_raws) or bin_path == base_skin_path:  # 跳过已处理的基础皮肤
                continue

            bin_raw = bin_raws[i]
            if not bin_raw:
                continue

            # 获取该BIN文件对应的映射信息
            mapping_info = bin_mapping.get(bin_path)
            if not mapping_info:
                continue

            try:
                bin_file = BIN(bin_raw)

                # 处理主题音乐 - 非基础皮肤也可能有主题音乐
                if bin_file.theme_music:
                    skin_id = None
                    if mapping_info["type"] == "skin":
                        skin_id = champion_data["skins"][mapping_info["index"]].get("id")
                    elif mapping_info["type"] == "chroma":
                        skin_idx = mapping_info["skin_index"]
                        chroma_idx = mapping_info["chroma_index"]
                        skin_id = champion_data["skins"][skin_idx]["chromas"][chroma_idx].get("id")

                    if skin_id:
                        logger.info(f"发现皮肤 {skin_id} 的主题音乐 数量: {len(bin_file.theme_music)}")
                        # 暂不做任何处理
                        # if "themeMusic" not in champion_data:
                        #     champion_data["themeMusic"] = {}
                        # champion_data["themeMusic"][str(skin_id)] = bin_file.theme_music

                # 收集当前皮肤的所有音频数据
                skin_audio_data = self._collect_skin_audio_data(bin_file, base_categories)

                # 更新皮肤或炫彩的音频数据
                self._update_skin_audio_data(champion_data, mapping_info, skin_audio_data)

            except Exception as e:
                logger.error(f"解析BIN文件失败: {bin_path}, 错误: {e}")
                logger.debug(traceback.format_exc())

    def _collect_skin_audio_data(self, bin_file: BIN, base_categories: dict[str, list[str]]) -> AudioData:
        """
        从BIN文件中收集皮肤的音频数据

        :param bin_file: BIN文件对象
        :param base_categories: 基础皮肤的音频分类信息，用于去重
        :return: 收集到的音频数据
        """
        skin_audio_data = {}

        for _type, category, bank_path in self._iterate_bin_banks(bin_file):
            # 检查是否是基础皮肤已有的类别
            is_base_category = False
            if _type in base_categories and category in base_categories[_type]:
                is_base_category = True

            # 如果不是基础皮肤的类别，则添加
            if not is_base_category:
                if _type not in skin_audio_data:
                    skin_audio_data[_type] = []
                skin_audio_data[_type].append(bank_path)

        return skin_audio_data

    def _update_skin_audio_data(
        self, champion_data: ChampionData, mapping_info: dict[str, Any], skin_audio_data: AudioData
    ) -> None:
        """
        更新皮肤或炫彩的音频数据

        :param champion_data: 英雄数据
        :param mapping_info: 映射信息
        :param skin_audio_data: 音频数据
        """
        if mapping_info["type"] == "skin":
            # 初始化皮肤的audioData结构
            if "audioData" not in champion_data["skins"][mapping_info["index"]]:
                champion_data["skins"][mapping_info["index"]]["audioData"] = {}

            # 更新普通皮肤的音频数据
            for _type, paths in skin_audio_data.items():
                if paths:  # 只有当有数据时才更新
                    champion_data["skins"][mapping_info["index"]]["audioData"][_type] = paths
        else:  # 处理炫彩皮肤
            skin_idx = mapping_info["skin_index"]
            chroma_idx = mapping_info["chroma_index"]

            # 初始化炫彩皮肤的audioData结构
            if "audioData" not in champion_data["skins"][skin_idx]["chromas"][chroma_idx]:
                champion_data["skins"][skin_idx]["chromas"][chroma_idx]["audioData"] = {}

            # 更新炫彩皮肤的音频数据
            for _type, paths in skin_audio_data.items():
                if paths:  # 只有当有数据时才更新
                    champion_data["skins"][skin_idx]["chromas"][chroma_idx]["audioData"][_type] = paths

    def _parse_skin_id(self, full_id: int, champion_id: int) -> int:
        """
        从完整的皮肤ID中提取皮肤编号

        :param full_id: 完整ID，如1001
        :param champion_id: 英雄ID，如1
        :return: 皮肤编号，如1
        """
        # 将champion_id转为字符串，计算位数
        champion_id_len = len(str(champion_id))

        # 将完整ID转为字符串，截取champion_id之后的部分
        skin_id_str = str(full_id)[champion_id_len:]

        # 转回整数（会自动去除前导零）
        return int(skin_id_str)

    def _get_game_version(self) -> str:
        """
        获取游戏版本

        :return: 游戏版本号
        """
        meta = self.game_path / "Game" / "content-metadata.json"
        if not meta.exists():
            raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

        with open(meta, encoding="utf-8") as f:
            data = json.load(f)

        version_v = data["version"]

        if m := re.match(r"^(\d+\.\d+)\.", version_v):
            return m.group(1)

        raise ValueError(f"无法解析版本号: {version_v}")

    def _extract_wad_data(self, out_dir: StrPath, region: str) -> None:
        """
        从WAD文件提取JSON数据

        :param out_dir: 输出目录
        :param region: 地区代码
        """
        out_path = Path(out_dir) / self.version / region
        out_path.mkdir(parents=True, exist_ok=True)

        # 处理en_US为default
        _region = "default" if region.lower() == "en_us" else region

        # 获取WAD文件路径
        _head = format_region(_region)
        if _head == "default":
            wad_files = list(self.game_path.glob("LeagueClient/Plugins/rcp-be-lol-game-data/default-assets*.wad"))
        else:
            wad_files = [self.game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data" / f"{_head}-assets.wad"]

        if not wad_files or not wad_files[0].exists():
            logger.error(f"未找到 {_region} 区域的WAD文件")
            return

        # 哈希表
        hash_table = [
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champion-summary.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skinlines.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/skins.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/maps.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/items.json",
            f"plugins/rcp-be-lol-game-data/global/{_region}/v1/universes.json",
        ]

        # 输出路径转换
        def output_file_name(path: str) -> Path:
            reg = re.compile(rf"plugins/rcp-be-lol-game-data/global/{_region}/v1/", re.IGNORECASE)
            new = reg.sub("", path)
            return out_path / new

        # 解包WAD文件
        for wad_file in wad_files:
            WAD(wad_file).extract(hash_table, output_file_name)

        # 获取英雄概要以解包所有英雄详细信息
        try:
            summary_file = out_path / "champion-summary.json"
            if summary_file.exists():
                with open(summary_file, encoding="utf-8") as f:
                    champions = json.load(f)

                # 提取每个英雄的详细信息
                champion_hashes = [
                    f"plugins/rcp-be-lol-game-data/global/{_region}/v1/champions/{item['id']}.json"
                    for item in champions
                    if item["id"] != -1
                ]

                # 创建champions目录
                (out_path / "champions").mkdir(exist_ok=True)

                # 解包英雄详细信息
                for wad_file in wad_files:
                    WAD(wad_file).extract(champion_hashes, output_file_name)

        except Exception as e:
            logger.error(f"解包英雄信息时出错: {str(e)}")
            logger.debug(traceback.format_exc())

    def _merge_language_data(self, out_dir: StrPath) -> None:
        """
        合并多种语言的JSON数据

        :param out_dir: 输出目录基础路径
        """
        base_path = Path(out_dir) / self.version

        # 确保default在语言列表中
        if "default" not in self.process_languages:
            logger.error("语言列表必须包含'default'")
            return

        # 第一步：读取所有语言的champion-summary.json
        champion_summaries = self._load_language_summaries(base_path, self.process_languages)

        # 如果没有找到default语言的数据，无法继续
        if "default" not in champion_summaries:
            logger.error("未找到default语言的英雄概要数据，无法处理")
            return

        # 检查各个语言文件的字段情况
        field_availability = self._analyze_field_availability(champion_summaries)

        # 初始化结果结构
        self._initialize_result_structure()

        # 创建进度跟踪器
        champions_count = len(champion_summaries["default"])
        progress = ProgressTracker(champions_count, "英雄数据处理", log_interval=10)

        # 处理default语言的英雄数据
        self._process_default_champions(champion_summaries["default"], field_availability, base_path, progress)

        # 处理其他语言的数据
        self._merge_other_languages(field_availability, base_path, champion_summaries)

        progress.finish()

        # 创建索引并完成结果
        final_result = self._finalize_result()

        # 保存合并后的数据
        merged_file = base_path / "merged_data.json"
        dump_json(final_result, merged_file)

    def _merge_other_languages(self, field_availability: dict, base_path: Path, champion_summaries: dict) -> None:
        """
        处理并合并其他语言的数据

        :param champion_summaries: 各语言的英雄概要数据
        :param field_availability: 字段可用性信息
        :param base_path: 基础路径
        """
        for language in self.process_languages:
            if language != "default" and language.lower() != "en_us" and language in champion_summaries:
                self._process_other_language_data(champion_summaries[language], field_availability, base_path, language)

    def _build_champion_data(self, champion: dict, champ_id: str, has_description: bool, default_path: Path) -> None:
        """
        构建单个英雄的基础数据

        :param champion: 英雄基本数据
        :param champ_id: 英雄ID(字符串)
        :param has_description: 是否包含描述字段
        :param default_path: 英雄详情文件路径
        """
        # 创建英雄基本结构
        self.result["champions"][champ_id] = {
            "id": champion["id"],
            "alias": champion["alias"],
            # "contentId": champion["contentId"],
            "names": {"default": champion["name"]},
        }

        # 仅在默认语言有description字段时添加
        if has_description and "description" in champion:
            self.result["champions"][champ_id]["descriptions"] = {"default": champion["description"]}

        # 添加WAD文件路径信息
        self._add_wad_paths(self.result["champions"][champ_id], champion["alias"])

        # 处理英雄详细信息
        self._process_champion_detail(champ_id, champion, default_path)

    def _load_language_summaries(self, base_path: Path, languages: list[str]) -> dict[str, list]:
        """
        读取所有语言的英雄概要数据

        :param base_path: 基础路径
        :param languages: 语言列表
        :return: 各语言的英雄概要数据
        """
        champion_summaries = {}
        for language in languages:
            lang_code = "default" if language.lower() == "en_us" else language
            lang_path = base_path / lang_code
            summary_file = lang_path / "champion-summary.json"

            if summary_file.exists():
                try:
                    with open(summary_file, encoding="utf-8") as f:
                        champion_summaries[lang_code] = json.load(f)
                        logger.info(f"已加载 {lang_code} 语言的英雄概要，{len(champion_summaries[lang_code])} 个英雄")
                except Exception as e:
                    logger.error(f"读取 {lang_code} 语言英雄概要失败: {str(e)}")

        return champion_summaries

    def _analyze_field_availability(self, champion_summaries: dict[str, list]) -> dict[str, set]:
        """
        分析各语言文件的字段可用性

        :param champion_summaries: 各语言的英雄概要数据
        :return: 各语言可用字段的集合
        """
        field_availability = {}
        for lang, champions in champion_summaries.items():
            # 用第一个英雄作为检查样本
            if champions and len(champions) > 0:
                sample_champion = champions[0]
                fields = set(sample_champion.keys())
                field_availability[lang] = fields
                logger.debug(f"{lang} 语言的champion字段: {fields}")
        return field_availability

    def _initialize_result_structure(self) -> None:
        """
        初始化结果数据结构

        :return: 初始化的结果字典
        """
        self.result = {
            "indices": {},  # 先预留索引位置
            "champions": {},
            "gameVersion": self.version,
            "lastUpdate": datetime.now().isoformat(),
        }

    def _process_default_champions(
        self,
        default_champions: list,
        field_availability: dict[str, set],
        base_path: Path,
        progress: ProgressTracker | None = None,
    ) -> None:
        """
        处理default语言的英雄数据

        :param result: 结果数据结构
        :param default_champions: default语言的英雄数据
        :param field_availability: 字段可用性信息
        :param base_path: 基础路径
        :param progress: 进度跟踪器，可选
        """
        default_path = base_path / "default" / "champions"

        # 检查默认语言中是否有description字段
        has_description = "description" in field_availability.get("default", set())

        # 遍历default语言的所有英雄
        for champion in default_champions:
            if champion["id"] == -1:  # 跳过"无"英雄
                continue

            champ_id = str(champion["id"])

            # 构建英雄数据并添加到结果中
            self._build_champion_data(champion, champ_id, has_description, default_path)

            # 更新进度
            if progress:
                progress.update()

    def _add_wad_paths(self, champion_data: dict, alias: str) -> None:
        """
        添加英雄的WAD文件路径信息

        :param champion_data: 英雄数据
        :param alias: 英雄别名
        """
        # 基础WAD文件路径
        root_wad_path = f"Game/DATA/FINAL/Champions/{alias}.wad.client"

        # 初始化wad字段
        champion_data["wad"] = {"root": root_wad_path}

        # 注意：这里不检查文件是否存在，因为这是一个静态方法，
        # 真正的文件检查会在调用方执行

    def _process_champion_detail(self, champ_id: str, champion: dict, champion_path: Path) -> None:
        """
        处理单个英雄的详细信息

        :param champ_id: 英雄ID
        :param champion: 英雄基本数据
        :param champion_path: 英雄详情文件路径
        """
        detail_file = champion_path / f"{champion['id']}.json"
        if not detail_file.exists():
            return

        try:
            with open(detail_file, encoding="utf-8") as f:
                champion_detail = json.load(f)

            # 添加title字段
            if "title" in champion_detail:
                self.result["champions"][champ_id]["titles"] = {"default": champion_detail["title"]}

            # 添加皮肤信息
            if "skins" in champion_detail:
                self.result["champions"][champ_id]["skins"] = self._process_champion_skins(champion_detail["skins"])

        except Exception as e:
            logger.error(f"处理英雄 {champion['id']} default语言详细信息失败: {str(e)}")

    def _process_champion_skins(self, skins: list) -> list:
        """
        处理英雄的皮肤信息

        :param skins: 皮肤数据列表
        :return: 处理后的皮肤数据列表
        """
        processed_skins = []

        for skin in skins:
            skin_data = {
                "id": skin["id"],
                "isBase": skin.get("isBase", False),
                # "contentId": skin.get("contentId", ""),
                "skinNames": {"default": skin["name"]},
                "audioData": {},  # 添加音频路径字段，初始为空字典
                "binPath": "",  # 添加BIN文件相对路径字段
            }

            # 处理炫彩皮肤
            if "chromas" in skin:
                skin_data["chromas"] = []
                for chroma in skin["chromas"]:
                    chroma_data = {
                        "id": chroma["id"],
                        "chromaNames": {"default": chroma.get("name", "")},
                        "audioData": {},  # 也为炫彩皮肤添加音频路径字段
                        "binPath": "",  # 添加BIN文件相对路径字段
                    }
                    skin_data["chromas"].append(chroma_data)

            processed_skins.append(skin_data)

        return processed_skins

    def _process_other_language_data(
        self, champions: list, field_availability: dict[str, set], base_path: Path, language: str
    ) -> None:
        """
        处理其他语言的数据

        :param champions: 该语言的英雄数据
        :param field_availability: 字段可用性信息
        :param base_path: 基础路径
        :param language: 语言代码
        """
        # 检查该语言是否有description字段
        lang_has_description = "description" in field_availability.get(language, set())

        # 检查default语言是否有description字段
        has_description = "description" in field_availability.get("default", set())

        # 遍历该语言的英雄概要
        for champion in champions:
            if champion["id"] == -1:
                continue

            champ_id = str(champion["id"])
            if champ_id not in self.result["champions"]:
                logger.warning(f"在 {language} 语言中发现default中不存在的英雄ID: {champ_id}，跳过")
                continue

            # 添加该语言的名称
            self.result["champions"][champ_id]["names"][language] = champion["name"]

            # 仅在该语言有description字段且总体有这个字段时添加description
            if has_description and lang_has_description and "description" in champion:
                if "descriptions" not in self.result["champions"][champ_id]:
                    self.result["champions"][champ_id]["descriptions"] = {}
                self.result["champions"][champ_id]["descriptions"][language] = champion["description"]

            # 处理该语言的英雄详细信息
            self._process_other_language_champion_detail(champ_id, champion, base_path, language)

    def _process_other_language_champion_detail(
        self, champ_id: str, champion: dict, base_path: Path, language: str
    ) -> None:
        """
        处理其他语言的英雄详细信息

        :param champ_id: 英雄ID
        :param champion: 英雄基本数据
        :param base_path: 基础路径
        :param language: 语言代码
        """
        detail_file = base_path / language / "champions" / f"{champion['id']}.json"
        if not detail_file.exists():
            return

        try:
            with open(detail_file, encoding="utf-8") as f:
                champion_detail = json.load(f)

            # 添加title字段
            if "title" in champion_detail:
                if "titles" not in self.result["champions"][champ_id]:
                    self.result["champions"][champ_id]["titles"] = {}
                self.result["champions"][champ_id]["titles"][language] = champion_detail["title"]

            # 处理皮肤名称翻译
            if "skins" in champion_detail and "skins" in self.result["champions"][champ_id]:
                self._process_other_language_skins(
                    self.result["champions"][champ_id]["skins"], champion_detail["skins"], language
                )

        except Exception as e:
            logger.error(f"处理英雄 {champion['id']} {language}语言详细信息失败: {str(e)}")

    def _process_other_language_skins(self, base_skins: list, lang_skins: list, language: str) -> None:
        """
        处理其他语言的皮肤信息

        :param base_skins: 基础皮肤数据
        :param lang_skins: 当前语言的皮肤数据
        :param language: 语言代码
        """
        for i, skin in enumerate(lang_skins):
            if i >= len(base_skins):
                break

            # 添加皮肤名称
            if "name" in skin:
                base_skins[i]["skinNames"][language] = skin["name"]

            # 处理炫彩皮肤名称
            if "chromas" in skin and "chromas" in base_skins[i]:
                for j, chroma in enumerate(skin["chromas"]):
                    if j < len(base_skins[i]["chromas"]):
                        base_skins[i]["chromas"][j]["chromaNames"][language] = chroma.get("name", "")

    def _create_indices(self) -> None:
        """
        创建数据索引
        """
        logger.info("正在创建索引...")

        # 按别名创建索引
        self.result["indices"]["alias"] = {}
        for champ_id, champion in self.result["champions"].items():
            alias = champion.get("alias", "").lower()
            if alias:
                self.result["indices"]["alias"][alias] = champ_id

        logger.info(f"索引创建完成: {len(self.result['indices']['alias'])} 个别名索引")

    def _finalize_result(self) -> dict:
        """
        完成结果，添加统计信息并整理结构

        :return: 最终的结果数据
        """
        # 添加WAD语言文件路径
        self._add_language_wad_paths()

        # 添加统计信息日志
        champion_count = len(self.result["champions"])
        languages_found = set()
        skin_count = 0

        # 收集统计数据
        for champ in self.result["champions"].values():
            languages_found.update(champ.get("names", {}).keys())
            skin_count += len(champ.get("skins", []))

        # 创建索引
        self._create_indices()

        # 添加语言信息（不包括默认的en_us/default）
        supported_languages = [lang for lang in self.process_languages if lang != "default" and lang.lower() != "en_us"]

        # 重新构建结果，确保顺序正确
        final_result = {
            "indices": self.result["indices"],
            "champions": self.result["champions"],
            "gameVersion": self.result["gameVersion"],
            "languages": supported_languages,
            "lastUpdate": self.result["lastUpdate"],
        }

        logger.info(f"合并完成: {champion_count} 个英雄, {skin_count} 个皮肤, 语言: {supported_languages}")

        return final_result

    def _add_language_wad_paths(self) -> None:
        """
        为每个英雄添加各语言的WAD文件路径
        """
        for lang in self.process_languages:
            if lang == "default" or lang.lower() == "en_us":
                continue  # 跳过default语言

            for _champion_id, champion_data in self.result["champions"].items():
                alias = champion_data.get("alias", "")
                if not alias:
                    continue

                # 添加该语言的WAD文件路径
                lang_wad_path = f"Game/DATA/FINAL/Champions/{alias}.{lang}.wad.client"
                if "wad" not in champion_data:
                    champion_data["wad"] = {}
                champion_data["wad"][lang] = lang_wad_path

    def _verify_wad_paths(self, temp_path: Path) -> None:
        """
        验证WAD文件路径是否存在，不存在则记录错误但保持路径信息

        :param temp_path: 临时目录路径
        """
        merged_file = temp_path / self.version / "merged_data.json"

        if not merged_file.exists():
            logger.error(f"合并数据文件不存在: {merged_file}")
            return

        try:
            # 使用common.py中的load_json函数
            data = load_json(merged_file)
            if not data:
                logger.error(f"无法加载合并数据文件: {merged_file}")
                return

            # 获取英雄总数并创建进度跟踪器
            champions = data.get("champions", {})
            champion_count = len(champions)
            progress = ProgressTracker(champion_count, "WAD路径验证", log_interval=10)
            missing_paths = 0

            # 遍历所有英雄
            for champion_id, champion_data in champions.items():
                if "wad" not in champion_data:
                    progress.update()
                    continue

                # 检查root WAD路径
                root_wad = champion_data["wad"].get("root")
                if root_wad:
                    full_path = self.game_path / root_wad
                    if not full_path.exists():
                        logger.warning(f"英雄 {champion_data.get('alias', champion_id)} 的根WAD文件不存在: {full_path}")
                        missing_paths += 1

                # 检查语言WAD路径
                for lang, lang_wad in champion_data["wad"].items():
                    if lang != "root":
                        full_path = self.game_path / lang_wad
                        if not full_path.exists():
                            logger.warning(
                                f"英雄 {champion_data.get('alias', champion_id)} 的 {lang} 语言WAD文件不存在: {full_path}"
                            )
                            missing_paths += 1

                progress.update()

            progress.finish()
            if missing_paths > 0:
                logger.warning(f"共有 {missing_paths} 个WAD文件路径不存在，但仍保留路径信息")

            # 使用common.py中的dump_json函数保存更新后的数据
            dump_json(data, merged_file)

        except Exception as e:
            logger.error(f"验证WAD路径时出错: {str(e)}")
            logger.debug(traceback.format_exc())


class DataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    def __init__(self, data_file: StrPath, default_language: str = "default"):
        """
        初始化数据读取器

        :param data_file: 合并后的JSON数据文件路径
        :param default_language: 默认使用的语言
        """
        # 防止单例被重复初始化
        if hasattr(self, "initialized"):
            return

        self.default_language = default_language
        self.data = self._load_data(data_file)
        self.version = self.data.get("gameVersion", "unknown")
        self.initialized = True

    def _load_data(self, data_file: StrPath) -> dict:
        """
        加载数据文件

        :param data_file: JSON数据文件路径
        :return: 加载的数据
        """
        data = load_json(data_file)
        if not data:
            logger.error(f"无法加载数据文件: {data_file}")
            return {"champions": {}, "gameVersion": "unknown"}
        return data

    def set_language(self, language: str) -> None:
        """
        设置默认语言

        :param language: 语言代码
        """
        self.default_language = language

    def get_languages(self) -> list[str]:
        """
        获取支持的语言列表

        :return: 语言代码列表
        """
        # 优先使用预计算的languages字段
        if "languages" in self.data:
            languages = set(self.data["languages"])
            languages.add("default")  # 确保default始终存在
            return list(languages)

        # 备选：从英雄数据中收集语言
        languages = set()
        for champion in self.data.get("champions", {}).values():
            languages.update(champion.get("names", {}).keys())
        return list(languages)

    def get_champion(self, champion_id: int) -> dict:
        """
        根据ID获取英雄信息

        :param champion_id: 英雄ID
        :return: 英雄信息
        """
        champ_id = str(champion_id)
        return self.data.get("champions", {}).get(champ_id, {})

    def find_champion(self, alias: str) -> dict:
        """
        根据别名获取英雄信息

        :param alias: 英雄别名
        :return: 英雄信息
        """
        # 使用索引查找
        if "indices" in self.data and "alias" in self.data.get("indices", {}):
            champ_id = self.data["indices"]["alias"].get(alias.lower())
            if champ_id:
                return self.data.get("champions", {}).get(champ_id, {})

        # 索引不存在或未找到，回退到传统查找方式
        for champion in self.data.get("champions", {}).values():
            if champion.get("alias", "").lower() == alias.lower():
                return champion
        return {}

    def get_champions(self) -> list[dict]:
        """
        获取所有英雄列表

        :return: 英雄列表
        """
        return list(self.data.get("champions", {}).values())
