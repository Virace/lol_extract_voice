# 🐍 In the face of ambiguity, refuse the temptation to guess.
# 🐼 面对不确定性，拒绝妄加猜测
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/7/30 7:41
# @Update  : 2025/8/3 15:22
# @Detail  : 数据读取器

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from lol_audio_unpack.manager.utils import read_data, resolve_context_version
from lol_audio_unpack.utils.common import Singleton
from lol_audio_unpack.utils.logging import performance_monitor

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext


def get_default_hidden_champion_markers(champion: Mapping[str, Any]) -> tuple[str, ...]:
    """返回英雄默认隐藏命中的稳定特征。

    说明：
        英雄名会随地区本地化变化，因此默认隐藏规则只依赖稳定字段：
        alias、根 WAD 文件名和 ID 前缀。
    """
    markers: list[str] = []

    alias = str(champion.get("alias", "")).strip().casefold()
    if alias.startswith("ruby_"):
        markers.append("alias:ruby")

    wad_info = champion.get("wad", {})
    wad_root = str(wad_info.get("root", "")) if isinstance(wad_info, dict) else ""
    wad_filename = Path(wad_root).name.casefold()
    if wad_filename.startswith("ruby_"):
        markers.append("wad:ruby")

    champion_id = str(champion.get("id", "")).strip()
    if champion_id.startswith("666"):
        markers.append("id:666")

    return tuple(markers)


def should_hide_champion_by_default(champion: Mapping[str, Any]) -> bool:
    """判断英雄是否应在默认列表与默认全量任务中隐藏。"""
    return bool(get_default_hidden_champion_markers(champion))


def filter_default_visible_champions(champions: Iterable[dict]) -> list[dict]:
    """过滤默认可见的英雄集合。"""
    return [champion for champion in champions if not should_hide_champion_by_default(champion)]


def get_default_visible_champions(reader: Any) -> list[dict]:
    """从读取器中获取默认可见的英雄集合。"""
    return filter_default_visible_champions(reader.get_champions())


class DataReader(metaclass=Singleton):
    """
    从合并后的数据文件读取游戏数据
    """

    CHECK_VERSION_DIFF = 2
    AUDIO_TYPE_VO = "VO"
    AUDIO_TYPE_SFX = "SFX"
    AUDIO_TYPE_MUSIC = "MUSIC"

    @logger.catch
    @performance_monitor(level="DEBUG")
    def __init__(self, ctx: AppContext):
        """
        初始化数据读取器

        从合并后的数据文件和分散的banks/events文件中读取游戏数据

        Args:
            ctx: 运行时上下文。
        """
        if hasattr(self, "initialized"):
            return

        self.ctx = ctx
        self.game_path = Path(self.ctx.config.game_path)
        self.manifest_path = Path(self.ctx.paths.manifest_path)

        if not self.game_path or not self.manifest_path:
            raise ValueError("GAME_PATH 和 MANIFEST_PATH 必须在配置中设置")

        self.version: str = resolve_context_version(self.ctx)
        self.version_manifest_path: Path = self.manifest_path / self.version

        # 使用不带后缀的基础路径，让read_data自动寻找最佳格式
        self.data = read_data(self.version_manifest_path / "data", dev_mode=self.ctx.config.dev_mode)
        if not self.data:
            raise FileNotFoundError("核心数据文件 (data.yml/json/msgpack) 不存在，请先运行更新程序。")

        # 校验数据版本
        self._validate_data_version()

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
        self._map_events_cache: dict[int, dict] = {}

        # 防御性开发：记录未知的音频分类
        self.unknown_categories: set[str] = set()
        self.initialized = True

    def _validate_data_version(self):
        """
        校验加载的数据文件版本与当前游戏版本的兼容性。

        - 大版本不一致: 抛出致命错误，程序终止。
        - 小版本差距过大 (>2): 记录错误日志，但程序继续。
        - 小版本差距较小 (<=2): 记录警告日志，程序继续。
        - 构建号不同: 忽略。
        """
        data_version_str = self.data.get("metadata", {}).get("gameVersion")
        if not data_version_str:
            logger.warning("数据文件中缺少 'gameVersion' 字段，无法进行版本校验。")
            return

        try:
            # 分割版本号，例如 "15.14" -> ["15", "14"]
            current_parts = self.version.split(".")
            data_parts = data_version_str.split(".")

            if len(current_parts) < self.CHECK_VERSION_DIFF or len(data_parts) < self.CHECK_VERSION_DIFF:
                logger.error(f"版本号格式无效。当前游戏: '{self.version}', 数据文件: '{data_version_str}'")
                return

            # 1. 检查大版本 (Major version)
            if current_parts[0] != data_parts[0]:
                error_msg = (
                    f"数据版本与游戏版本严重不匹配 (大版本不同)！\n"
                    f"  - 当前游戏版本: {self.version}\n"
                    f"  - 数据文件版本: {data_version_str}\n"
                    f"请立即运行数据更新程序。"
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)

            # 2. 检查小版本 (Minor version)
            current_minor = int(current_parts[1])
            data_minor = int(data_parts[1])
            minor_diff = abs(current_minor - data_minor)

            if minor_diff > 0:
                version_msg = (
                    f"数据版本与当前游戏版本存在差异。\n  - 游戏版本: {self.version}\n  - 数据版本: {data_version_str}"
                )
                if minor_diff > self.CHECK_VERSION_DIFF:
                    logger.error(
                        f"{version_msg}\n小版本差距过大(>{self.CHECK_VERSION_DIFF})，数据可能不准确，请立即更新数据。"
                    )
                else:
                    logger.warning(
                        f"{version_msg}\n小版本差距较小(≤{self.CHECK_VERSION_DIFF})，数据有可能不准确，建议更新数据。"
                    )

        except (ValueError, IndexError) as e:
            logger.error(f"解析版本号时出错: {e}。当前游戏: '{self.version}', 数据文件: '{data_version_str}'")
            return

    def get_audio_type(self, category: str) -> str:
        """从分类字符串中识别出音频的大类（VO, SFX, MUSIC）"""
        category_upper = category.upper()
        if "ANNOUNCER" in category_upper or "_VO" in category_upper:
            return self.AUDIO_TYPE_VO
        if category_upper.startswith("MUS_") or "MUSIC" in category_upper:
            return self.AUDIO_TYPE_MUSIC
        if "_SFX" in category_upper or category_upper == "INIT" or "HUD" in category_upper:
            return self.AUDIO_TYPE_SFX

        self.unknown_categories.add(category)
        return self.AUDIO_TYPE_SFX

    def get_languages(self) -> list[str]:
        """获取支持的语言列表"""
        languages = self.data.get("metadata", {}).get("languages", [])
        languages_set = set(languages)
        languages_set.add("default")
        return list(languages_set)

    @logger.catch
    @performance_monitor(level="DEBUG")
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
        banks_data = read_data(banks_file_base, dev_mode=self.ctx.config.dev_mode)

        if banks_data:
            self._champion_banks_cache[champion_id] = banks_data

        return banks_data

    @logger.catch
    @performance_monitor(level="DEBUG")
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
            logger.info(f"已记录 {len(new_unknowns)} 个新的未知音频分类")
        except Exception as e:
            logger.error(f"写入未知分类文件时出错: {e}")

    @logger.catch
    @performance_monitor(level="DEBUG")
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
        events_data = read_data(events_file_base, dev_mode=self.ctx.config.dev_mode)

        if events_data:
            self._champion_events_cache[champion_id] = events_data

        return events_data

    @logger.catch
    @performance_monitor(level="DEBUG")
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
        banks_data = read_data(banks_file_base, dev_mode=self.ctx.config.dev_mode)

        if banks_data:
            self._map_banks_cache[map_id] = banks_data

        return banks_data

    @logger.catch
    @performance_monitor(level="DEBUG")
    def get_map_events(self, map_id: int) -> dict | None:
        """读取并缓存指定地图的 events 数据。

        Args:
            map_id: 地图 ID。

        Returns:
            地图事件映射字典；读取失败时返回 ``None``。
        """
        if map_id in self._map_events_cache:
            return self._map_events_cache[map_id]

        events_file_base = self.map_events_dir / str(map_id)
        map_events_data = read_data(events_file_base, dev_mode=self.ctx.config.dev_mode)
        result = map_events_data.get("map") if map_events_data else None

        if result:
            self._map_events_cache[map_id] = result

        return result

    def get_champion(self, champion_id: int) -> dict:
        """根据ID获取英雄信息"""
        return self.data.get("champions", {}).get(str(champion_id), {})

    def get_champions(self) -> list[dict]:
        """获取所有英雄列表"""
        return list(self.data.get("champions", {}).values())

    def get_map(self, map_id: int) -> dict:
        """
        根据ID获取地图信息

        :param map_id: 地图ID
        :returns: 地图信息字典，失败时返回空字典
        """
        return self.data.get("maps", {}).get(str(map_id), {})

    def get_maps(self) -> list[dict]:
        """
        获取所有地图列表

        :returns: 地图信息列表
        """
        return list(self.data.get("maps", {}).values())
