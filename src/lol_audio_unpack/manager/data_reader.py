# 🐍 In the face of ambiguity, refuse the temptation to guess.
# 🐼 面对不确定性，拒绝妄加猜测
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:41
# @Update  : 2025/7/30 23:57
# @Detail  : 数据读取器


from pathlib import Path

from loguru import logger

from lol_audio_unpack.manager.utils import get_game_version, read_data
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.config import config


class DataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    AUDIO_TYPE_VO = "VO"
    AUDIO_TYPE_SFX = "SFX"
    AUDIO_TYPE_MUSIC = "MUSIC"
    KNOWN_AUDIO_TYPES = {AUDIO_TYPE_VO, AUDIO_TYPE_SFX, AUDIO_TYPE_MUSIC}

    def __init__(self):
        """
        初始化数据读取器

        从合并后的数据文件和分散的banks/events文件中读取游戏数据
        """
        if hasattr(self, "initialized"):
            return

        self.game_path: Path = config.GAME_PATH
        self.manifest_path: Path = config.MANIFEST_PATH
        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.version: str = get_game_version(self.game_path)
        self.version_manifest_path: Path = self.manifest_path / self.version

        # 使用不带后缀的基础路径，让read_data自动寻找最佳格式
        self.data = read_data(self.version_manifest_path / "data")

        # 更新为新的分散式文件结构路径
        self.champion_banks_dir: Path = self.version_manifest_path / "banks" / "champions"
        self.champion_events_dir: Path = self.version_manifest_path / "events" / "champions"
        self.map_banks_dir: Path = self.version_manifest_path / "banks" / "maps"
        self.map_events_dir: Path = self.version_manifest_path / "events" / "maps"
        self.unknown_categories_file: Path = self.version_manifest_path / "unknown-category.txt"

        # 简单缓存机制避免重复读取
        self._champion_banks_cache: dict[int, dict] = {}
        self._champion_events_cache: dict[int, dict] = {}
        self._map_banks_cache: dict[int, dict] = {}

        # 防御性开发：记录未知的音频分类
        self.unknown_categories: set[str] = set()
        self.initialized = True

    def get_audio_type(self, category: str) -> str:
        """从分类字符串中识别出音频的大类（VO, SFX, MUSIC）"""
        category_upper = category.upper()
        if "ANNOUNCER" in category_upper or "_VO" in category_upper:
            return self.AUDIO_TYPE_VO
        if category_upper.startswith("MUS_") or "MUSIC" in category_upper:
            return self.AUDIO_TYPE_MUSIC
        if "_SFX" in category_upper or category_upper == "INIT" or "HUD" in category_upper:
            return self.AUDIO_TYPE_SFX

        logger.warning(f"发现未知音频分类: '{category}'，已自动归类为SFX。")
        self.unknown_categories.add(category)
        return self.AUDIO_TYPE_SFX

    def get_languages(self) -> list[str]:
        """获取支持的语言列表"""
        languages = set(self.data.get("languages", []))
        languages.add("default")
        return list(languages)

    def get_champion_banks(self, champion_id: int) -> dict | None:
        """
        读取指定英雄的banks数据

        :param champion_id: 英雄ID
        :returns: 英雄banks数据字典，失败时返回None
        :rtype: dict | None
        """
        if champion_id in self._champion_banks_cache:
            return self._champion_banks_cache[champion_id]

        banks_file_base = self.champion_banks_dir / str(champion_id)
        banks_data = read_data(banks_file_base)

        if banks_data:
            self._champion_banks_cache[champion_id] = banks_data

        return banks_data

    def write_unknown_categories_to_file(self) -> None:
        """将本次运行中收集到的所有未知分类写入到文件中"""
        if not self.unknown_categories:
            return

        try:
            existing_unknowns = set()
            if self.unknown_categories_file.exists():
                with open(self.unknown_categories_file, encoding="utf-8") as f:
                    existing_unknowns = {line.strip() for line in f if line.strip()}

            new_unknowns = self.unknown_categories - existing_unknowns
            if not new_unknowns:
                return

            with open(self.unknown_categories_file, "a", encoding="utf-8") as f:
                for category in sorted(list(new_unknowns)):
                    f.write(f"{category}\n")
            logger.success(f"已将 {len(new_unknowns)} 个新的未知音频分类追加到: {self.unknown_categories_file}")
        except Exception as e:
            logger.error(f"写入未知分类文件时出错: {e}")

    def get_champion_events(self, champion_id: int) -> dict | None:
        """
        读取指定英雄的events数据

        :param champion_id: 英雄ID
        :returns: 英雄events数据字典，失败时返回None
        :rtype: dict | None
        """
        if champion_id in self._champion_events_cache:
            return self._champion_events_cache[champion_id]

        events_file_base = self.champion_events_dir / str(champion_id)
        events_data = read_data(events_file_base)

        if events_data:
            self._champion_events_cache[champion_id] = events_data

        return events_data

    def get_map_banks(self, map_id: int) -> dict | None:
        """
        读取指定地图的banks数据

        :param map_id: 地图ID
        :returns: 地图banks数据字典，失败时返回None
        :rtype: dict | None
        """
        if map_id in self._map_banks_cache:
            return self._map_banks_cache[map_id]

        banks_file_base = self.map_banks_dir / str(map_id)
        banks_data = read_data(banks_file_base)

        if banks_data:
            self._map_banks_cache[map_id] = banks_data

        return banks_data

    def get_map_events(self, map_id: int) -> dict | None:
        """
        读取指定地图的events数据

        :param map_id: 地图ID
        :returns: 地图events数据字典，失败时返回None
        :rtype: dict | None
        """
        events_file_base = self.map_events_dir / str(map_id)
        map_events_data = read_data(events_file_base)
        return map_events_data.get("map") if map_events_data else None

    def get_champion(self, champion_id: int) -> dict:
        """根据ID获取英雄信息"""
        return self.data.get("champions", {}).get(str(champion_id), {})

    def find_champion(self, alias: str) -> dict:
        """根据别名获取英雄信息"""
        if champ_id := self.data.get("indices", {}).get("alias", {}).get(alias.lower()):
            return self.get_champion(int(champ_id))
        return {}

    def get_champions(self) -> list[dict]:
        """获取所有英雄列表"""
        return list(self.data.get("champions", {}).values())
