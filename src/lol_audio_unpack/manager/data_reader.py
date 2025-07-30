# 🐍 In the face of ambiguity, refuse the temptation to guess.
# 🐼 面对不确定性，拒绝妄加猜测
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:41
# @Update  : 2025/7/30 8:38
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

    def __init__(self, default_language: str = "default"):
        """初始化数据读取器"""
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
        self.bin_data = read_data(self.version_manifest_path / "skins-bank-paths")
        self.map_bin_data = read_data(self.version_manifest_path / "maps-bank-paths")

        self.skin_events_dir: Path = self.version_manifest_path / "events" / "skins"
        self.map_events_dir: Path = self.version_manifest_path / "events" / "maps"
        self.unknown_categories_file: Path = self.version_manifest_path / "unknown-category.txt"

        self.default_language = default_language
        self.unknown_categories = set()
        self.initialized = True

    def set_language(self, language: str) -> None:
        """设置默认语言"""
        self.default_language = language

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

    def get_skin_bank(self, skin_id: int) -> dict:
        """根据皮肤ID获取其所有音频资源集合数据"""
        skin_id_str = str(skin_id)
        mappings = self.bin_data.get("skinAudioMappings", {})
        skins_data = self.bin_data.get("skins", {})

        mapping_info = mappings.get(skin_id_str)
        if isinstance(mapping_info, str):
            return self.get_skin_bank(int(mapping_info))

        result = skins_data.get(skin_id_str, {}).copy()
        if isinstance(mapping_info, dict):
            for category, owner_id in mapping_info.items():
                owner_data = skins_data.get(owner_id, {})
                if category in owner_data:
                    result[category] = owner_data[category]

        return result

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

    def get_skin_events(self, skin_id: int) -> dict | None:
        """按需加载并返回指定皮肤的事件数据"""
        skin_id_str = str(skin_id)
        champion_id = self.bin_data.get("skinToChampion", {}).get(skin_id_str)
        if not champion_id:
            return None

        event_file_base = self.skin_events_dir / f"{champion_id}"
        all_champion_events = read_data(event_file_base)
        return all_champion_events.get("skins", {}).get(skin_id_str) if all_champion_events else None

    def get_map_events(self, map_id: int) -> dict | None:
        """按需加载并返回指定地图的事件数据"""
        event_file_base = self.map_events_dir / f"{map_id}"
        map_events_data = read_data(event_file_base)
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
