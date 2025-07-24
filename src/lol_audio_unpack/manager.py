# 🐍 Explicit is better than implicit.
# 🐼 明了优于隐晦
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2024/5/6 1:19
# @Update  : 2025/7/25 4:58
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


def get_game_version(game_path: Path) -> str:
    """
    获取游戏版本

    :param game_path: 游戏根目录路径
    :return: 游戏版本号
    """
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.exists():
        raise FileNotFoundError("content-metadata.json 文件不存在，无法判断版本信息")

    with open(meta, encoding="utf-8") as f:
        data = json.load(f)

    version_v = data["version"]

    if m := re.match(r"^(\d+\.\d+)\.", version_v):
        return m.group(1)

    raise ValueError(f"无法解析版本号: {version_v}")


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
        self.version: str = get_game_version(self.game_path)
        # 特定版本的数据清单文件目录
        self.version_manifest_path: Path = self.manifest_path / self.version
        # 最终合并的数据文件路径
        self.data_file: Path = self.version_manifest_path / "data.json"
        # 实际处理的语言列表，包含 "default"
        self.process_languages: list[str] = self._prepare_language_list(self.languages)

        # 确保版本清单目录存在
        self.version_manifest_path.mkdir(parents=True, exist_ok=True)

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

    def check_and_update(self) -> Path:
        """
        检查游戏版本并更新数据

        :return: 合并后的数据文件路径
        """
        # 检查是否需要更新
        if not self._needs_update():
            return self.data_file

        # 使用config中的TEMP_PATH创建本次运行的临时目录
        # 通过添加时间戳确保每次运行的目录唯一
        run_temp_path = self.temp_path / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        run_temp_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建临时目录用于解包: {run_temp_path}")

        try:
            # 提取和处理数据
            self._process_data(run_temp_path)
            logger.success(f"数据更新完成: {self.data_file}")
            return self.data_file
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

    def _needs_update(self) -> bool:
        """
        检查是否需要更新数据

        :return: 是否需要更新
        """
        if not self.data_file.exists():
            return True

        try:
            with open(self.data_file, encoding="utf-8") as f:
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
        self._merge_and_build_data(temp_path)

        # 将合并后的数据文件复制到输出目录
        temp_data_file = temp_path / self.version / "data.json"
        if temp_data_file.exists():
            self.version_manifest_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_data_file, self.data_file)
            logger.info(f"已复制合并数据到: {self.data_file}")
        else:
            raise FileNotFoundError(f"未能创建合并数据文件: {temp_data_file}")

    def _load_language_json(self, base_path: Path, filename_template: str) -> dict[str, Any]:
        """
        加载指定模板的、所有语言的JSON文件

        :param base_path: 版本基础路径
        :param filename_template: 文件名模板，用{lang}作为语言占位符
        :return: 一个字典，键是语言代码，值是加载的JSON数据
        """
        loaded_data = {}
        for lang in self.process_languages:
            file_path = base_path / lang / filename_template.format(lang=lang)
            if file_path.exists():
                loaded_data[lang] = load_json(file_path)
            else:
                logger.warning(f"未找到JSON文件: {file_path}")
        return loaded_data

    def _merge_and_build_data(self, temp_dir: Path) -> None:
        """
        聚合所有数据处理和合并逻辑，生成最终的data.json

        :param temp_dir: 包含已提取数据的临时目录
        """
        base_path = temp_dir / self.version
        summaries = self._load_language_json(base_path, "champion-summary.json")

        if "default" not in summaries:
            logger.error("未找到default语言的英雄概要数据，无法继续处理")
            return

        final_champions = {}
        progress = ProgressTracker(len(summaries["default"]), "英雄数据合并", log_interval=10)

        for i, default_summary in enumerate(summaries["default"]):
            champ_id = str(default_summary["id"])
            if champ_id == "-1":
                continue

            alias = default_summary["alias"]
            details = self._load_language_json(base_path, f"champions/{champ_id}.json")
            default_details = details.get("default", {})

            # 1. 合并英雄基础信息 (name, title, description)
            names = {lang: summ[i]["name"] for lang, summ in summaries.items() if i < len(summ)}
            titles = {lang: det.get("title", "") for lang, det in details.items()}
            descriptions = {lang: summ[i].get("description", "") for lang, summ in summaries.items() if i < len(summ)}

            # 2. 构建皮肤和炫彩信息
            processed_skins = []
            for i, skin_detail in enumerate(default_details.get("skins", [])):
                skin_id_num = self._parse_skin_id(skin_detail["id"], int(champ_id))
                skin_names = {
                    lang: det.get("skins", [])[i].get("name", "")
                    for lang, det in details.items()
                    if i < len(det.get("skins", []))
                }

                skin_data = {
                    "id": skin_detail["id"],
                    "isBase": skin_detail.get("isBase", False),
                    "skinNames": skin_names,
                    "binPath": f"data/characters/{alias}/skins/skin{skin_id_num}.bin",
                }

                processed_chromas = []
                for j, chroma_detail in enumerate(skin_detail.get("chromas", [])):
                    chroma_id_num = self._parse_skin_id(chroma_detail["id"], int(champ_id))
                    chroma_names = {
                        lang: det.get("skins", [])[i].get("chromas", [])[j].get("name", "")
                        for lang, det in details.items()
                        if i < len(det.get("skins", [])) and j < len(det.get("skins", [])[i].get("chromas", []))
                    }
                    processed_chromas.append(
                        {
                            "id": chroma_detail["id"],
                            "chromaNames": chroma_names,
                            "binPath": f"data/characters/{alias}/skins/skin{chroma_id_num}.bin",
                        }
                    )

                if processed_chromas:
                    skin_data["chromas"] = processed_chromas

                processed_skins.append(skin_data)

            # 3. 组合最终的英雄数据
            final_champions[champ_id] = {
                "id": default_summary["id"],
                "alias": alias,
                "names": names,
                "titles": titles,
                "descriptions": {k: v for k, v in descriptions.items() if v},  # 过滤空描述
                "skins": processed_skins,
                "wad": {
                    "root": f"Game/DATA/FINAL/Champions/{alias}.wad.client",
                    **{
                        lang: f"Game/DATA/FINAL/Champions/{alias}.{lang}.wad.client"
                        for lang in self.process_languages
                        if lang != "default"
                    },
                },
            }
            progress.update()
        progress.finish()

        # 4. 构建最终结果文件
        final_result = {
            "indices": {"alias": {champ["alias"].lower(): champ_id for champ_id, champ in final_champions.items()}},
            "champions": final_champions,
            "gameVersion": self.version,
            "languages": [lang for lang in self.process_languages if lang != "default"],
            "lastUpdate": datetime.now().isoformat(),
        }

        # 5. 保存
        dump_json(final_result, base_path / "data.json")

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


class BinUpdater:
    """
    负责从BIN文件提取音频数据并更新到数据文件中
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

    def __init__(self):
        """
        初始化BIN音频更新器
        """
        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version
        self.data_file: Path = self.version_manifest_path / "data.json"
        self.bin_file: Path = self.version_manifest_path / "bin.json"

    def update(self) -> Path:
        """
        处理BIN文件，提取音频路径并创建独立的bin.json文件

        :return: 更新后的数据文件路径
        """
        if not self.data_file.exists():
            logger.error(f"数据文件不存在，请先运行DataUpdater: {self.data_file}")
            raise FileNotFoundError(f"数据文件不存在: {self.data_file}")

        try:
            data = load_json(self.data_file)
            if not data:
                logger.error(f"无法加载数据文件: {self.data_file}")
                raise ValueError(f"无法加载或解析JSON文件: {self.data_file}")

            # 初始化新的bin.json结构
            self.bin_result = {
                "gameVersion": self.version,
                "languages": data.get("languages", []),
                "lastUpdate": datetime.now().isoformat(),
                "champions": {},
            }

            # 获取英雄总数并创建进度跟踪器
            champions = data.get("champions", {})
            champion_count = len(champions)
            progress = ProgressTracker(champion_count, "英雄音频数据处理", log_interval=5)

            # 遍历所有英雄
            for champion_id, champion_data in champions.items():
                self._extract_champion_audio(champion_data, champion_id)
                progress.update()

            progress.finish()

            dump_json(self.bin_result, self.bin_file)
            logger.success(f"音频数据更新完成: {self.bin_file}")
            return self.bin_file

        except Exception as e:
            logger.error(f"处理BIN文件时出错: {str(e)}")
            logger.debug(traceback.format_exc())
            raise

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

        # 1. 收集所有路径并创建 path -> skin_id 的简单映射
        path_to_skin_id_map = {}
        base_skin_bin_path = None
        for skin in champion_data.get("skins", []):
            if skin.get("binPath"):
                path_to_skin_id_map[skin["binPath"]] = str(skin["id"])
                if skin.get("isBase"):
                    base_skin_bin_path = skin["binPath"]
            for chroma in skin.get("chromas", []):
                if chroma.get("binPath"):
                    path_to_skin_id_map[chroma["binPath"]] = str(chroma["id"])

        if not path_to_skin_id_map:
            return

        bin_paths = list(path_to_skin_id_map.keys())

        # 获取基础WAD路径
        root_wad_path = champion_data["wad"].get("root")
        if not root_wad_path:
            return

        full_wad_path = self.game_path / root_wad_path
        if not full_wad_path.exists():
            logger.error(f"英雄 {alias} 的WAD文件不存在: {full_wad_path}")
            return

        # 2. 一次性提取所有BIN文件
        try:
            logger.debug(f"从 {alias} 提取 {len(bin_paths)} 个BIN文件")
            bin_raws = WAD(full_wad_path).extract(bin_paths, raw=True)
            raw_data_map = dict(zip(bin_paths, bin_raws, strict=False))
        except Exception as e:
            logger.error(f"处理英雄 {alias} 的BIN文件时出错: {str(e)}")
            logger.debug(traceback.format_exc())
            return

        # 3. 首先处理基础皮肤，以获取用于去重的音频类别
        base_categories = {}
        if base_skin_bin_path and base_skin_bin_path in raw_data_map:
            bin_raw = raw_data_map.get(base_skin_bin_path)
            if bin_raw:
                try:
                    bin_file = BIN(bin_raw)
                    base_skin_audio_data = {}
                    for _type, category, bank_path in self._iterate_bin_banks(bin_file):
                        # 收集类别用于后续去重
                        if _type not in base_categories:
                            base_categories[_type] = []
                        base_categories[_type].append(category)

                        # 收集音频数据
                        if _type not in base_skin_audio_data:
                            base_skin_audio_data[_type] = []
                        base_skin_audio_data[_type].append(bank_path)

                    # 将基础皮肤的音频数据写入最终结果
                    if base_skin_audio_data:
                        base_skin_id = path_to_skin_id_map[base_skin_bin_path]
                        self.bin_result["champions"][base_skin_id] = base_skin_audio_data
                except Exception as e:
                    logger.error(f"解析基础皮肤BIN文件失败: {base_skin_bin_path}, 错误: {e}")
                    logger.debug(traceback.format_exc())

        # 4. 处理所有其他皮肤和炫彩
        for path, skin_id in path_to_skin_id_map.items():
            if path == base_skin_bin_path:
                continue  # 跳过已处理的基础皮肤

            bin_raw = raw_data_map.get(path)
            if not bin_raw:
                continue

            try:
                bin_file = BIN(bin_raw)
                # 收集音频数据，并根据基础皮肤的类别进行去重
                skin_audio_data = self._collect_skin_audio_data(bin_file, base_categories)

                # 将去重后的音频数据写入最终结果
                if skin_audio_data:
                    self.bin_result["champions"][skin_id] = skin_audio_data
            except Exception as e:
                logger.error(f"解析BIN文件失败: {path}, 错误: {e}")
                logger.debug(traceback.format_exc())

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

    def _collect_skin_audio_data(self, bin_file: BIN, base_categories: dict[str, list[str]]) -> AudioData:
        """
        从BIN文件中收集皮肤的音频数据，并根据基础皮肤类别去重

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


class DataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    def __init__(self, default_language: str = "default"):
        """
        初始化数据读取器

        :param default_language: 默认使用的语言
        """
        # 防止单例被重复初始化
        if hasattr(self, "initialized"):
            return

        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version

        data_file = self.version_manifest_path / "data.json"
        bin_file = self.version_manifest_path / "bin.json"

        self.data = self._load_data(data_file)
        self.bin_data = self._load_data(bin_file)
        self.default_language = default_language
        self.initialized = True

    def _load_data(self, data_file: StrPath) -> dict:
        """
        加载数据文件

        :param data_file: JSON数据文件路径
        :return: 加载的数据
        """
        path = Path(data_file)
        if not path.exists():
            logger.warning(f"数据文件不存在: {data_file}，将返回空字典")
            return {}

        data = load_json(path)
        if not data:
            logger.error(f"无法加载数据文件: {data_file}")
            return {}
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

    def get_skin_bank(self, skin_id: int) -> dict:
        """
        根据皮肤ID获取音频资源集合数据

        :param skin_id: 皮肤ID
        :return: 音频数据
        """
        return self.bin_data.get("champions", {}).get(str(skin_id), {})

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
