# 🐍 There should be one-- and preferably only one --obvious way to do it.
# 🐼 任何问题应有一种，且最好只有一种，显而易见的解决方法
# @Author  : Virace
# @Email   : Virace@aliyun.com
# @Site    : x-item.com
# @Software: Pycharm
# @Create  : 2025/8/4 13:03
# @Update  : 2025/8/7 11:00
# @Detail  : 共用数据模型和工具函数


from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.utils.common import sanitize_filename
from lol_audio_unpack.utils.config import config
from lol_audio_unpack.utils.deprecation import warn_legacy_global_mode

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppConfig, AppContext


def _resolve_app_config(
    ctx: "AppContext | None" = None,
    app_config: "AppConfig | None" = None,
) -> "AppConfig | None":
    """解析当前调用应使用的应用配置对象。"""
    if ctx is not None:
        return ctx.config
    if app_config is None:
        warn_legacy_global_mode("model")
    return app_config


def _resolve_game_path(
    ctx: "AppContext | None" = None,
    app_config: "AppConfig | None" = None,
) -> Path:
    """解析游戏根目录路径。"""
    resolved = _resolve_app_config(ctx=ctx, app_config=app_config)
    if resolved is not None:
        return resolved.game_path
    return Path(config.GAME_PATH)


def _resolve_game_region(
    ctx: "AppContext | None" = None,
    app_config: "AppConfig | None" = None,
) -> str:
    """解析当前语言区域。"""
    resolved = _resolve_app_config(ctx=ctx, app_config=app_config)
    if resolved is not None and resolved.game_region:
        return resolved.game_region
    return str(config.GAME_REGION)


@dataclass
class AudioEntityData:
    """音频实体统一数据结构

    :param entity_id: 实体ID（英雄ID或地图ID）
    :param entity_name: 实体名称（英雄名或地图名）
    :param entity_alias: 实体别名（英雄alias或地图mapStringId）
    :param entity_title: 实体标题（英雄称号或地图描述）
    :param entity_type: 实体类型（"champion" 或 "map"）
    :param sub_entities: 子实体数据（皮肤数据或地图本身）
    :param wad_root: 根WAD文件路径（用于SFX/Music）
    :param wad_language: 语言WAD文件路径（用于VO），None表示无语言WAD
    :param events: 事件数据（仅映射时使用），None表示不包含事件数据
    """

    entity_id: str
    entity_name: str
    entity_alias: str
    entity_title: str
    entity_type: str  # "champion" | "map"
    sub_entities: dict[str, dict[str, Any]]
    wad_root: str
    wad_language: str | None = None
    events: dict[str, dict[str, Any]] | None = None

    def get_sub_entity_info(self, sub_id: str) -> dict[str, Any] | None:
        """获取子实体的信息（皮肤或地图信息）

        :param sub_id: 子实体ID（皮肤ID或地图ID）
        :returns: 包含id和name的字典，不存在时返回None
        """
        sub_entity = self.sub_entities.get(sub_id)
        if not sub_entity:
            return None

        return {"id": int(sub_id), "name": sub_entity["name"]}

    def get_wad_path(
        self,
        audio_type: str,
        ctx: "AppContext | None" = None,
        app_config: "AppConfig | None" = None,
    ) -> Path | None:
        """根据音频类型获取对应的WAD文件完整路径

        :param audio_type: 音频类型（"VO"需要语言WAD，其他使用根WAD）
        :param ctx: 可选运行时上下文，传入时优先使用 ``ctx.config``。
        :param app_config: 可选应用配置对象，作为 ``ctx`` 的后备。
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
        full_path = _resolve_game_path(ctx=ctx, app_config=app_config) / relative_path
        return full_path if full_path.exists() else None

    @classmethod
    def from_champion(
        cls,
        champion_id: int,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: "AppContext | None" = None,
        app_config: "AppConfig | None" = None,
    ) -> "AudioEntityData":
        """从英雄数据创建AudioEntityData实例

        :param champion_id: 英雄ID
        :param reader: 数据读取器实例
        :param include_events: 是否包含事件数据（用于映射功能）
        :param ctx: 可选运行时上下文，传入时优先使用 ``ctx.config``。
        :param app_config: 可选应用配置对象，作为 ``ctx`` 的后备。
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
        language = _resolve_game_region(ctx=ctx, app_config=app_config)
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

        # 获取事件数据（如果需要）
        events_data = None
        if include_events:
            champion_events = reader.get_champion_events(champion_id)
            events_data = champion_events.get("skins", {}) if champion_events else {}

        # 安全化英雄名称和标题
        champion_name_raw = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))
        safe_champion_name = sanitize_filename(champion_name_raw)
        safe_champion_alias = sanitize_filename(champion.get("alias", "").lower())

        # 获取英雄标题（称号）
        champion_title_raw = champion.get("titles", {}).get(language, champion.get("titles", {}).get("default", ""))
        safe_champion_title = sanitize_filename(champion_title_raw) if champion_title_raw else None

        return cls(
            entity_id=str(champion_id),
            entity_name=safe_champion_name,
            entity_alias=safe_champion_alias,
            entity_title=safe_champion_title,
            entity_type="champion",
            sub_entities=sub_entities,
            wad_root=wad_root,
            wad_language=wad_language,
            events=events_data,
        )

    @classmethod
    def from_map(
        cls,
        map_id: int,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: "AppContext | None" = None,
        app_config: "AppConfig | None" = None,
    ) -> "AudioEntityData":
        """从地图数据创建AudioEntityData实例

        :param map_id: 地图ID
        :param reader: 数据读取器实例
        :param include_events: 是否包含事件数据（用于映射功能）
        :param ctx: 可选运行时上下文，传入时优先使用 ``ctx.config``。
        :param app_config: 可选应用配置对象，作为 ``ctx`` 的后备。
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
        language = _resolve_game_region(ctx=ctx, app_config=app_config)
        wad_language = wad_info.get(language)  # 可能为None，某些地图可能没有语言WAD

        # 获取地图名称（支持本地化）
        map_name_raw = map_info.get("names", {}).get(language, map_info.get("names", {}).get("default", ""))
        safe_map_name = sanitize_filename(map_name_raw)

        # 获取地图别名
        map_alias_raw = "common" if map_id == 0 else map_info.get("mapStringId", "").lower()
        safe_map_alias = sanitize_filename(map_alias_raw)

        # 地图作为自己的唯一"子实体"
        sub_entities = {str(map_id): {"name": safe_map_name, "categories": map_banks.get("banks", {})}}

        # 获取事件数据（如果需要）
        events_data = None
        if include_events:
            map_events_data = reader.get_map_events(map_id)
            # 地图事件数据结构稍有不同，需要包装成类似皮肤的格式
            events_data = {str(map_id): {"events": map_events_data.get("events", {})}} if map_events_data else {}

        return cls(
            entity_id=str(map_id),
            entity_name=safe_map_name,
            entity_alias=safe_map_alias,
            entity_title=None,  # 地图暂时不使用 title
            entity_type="map",
            sub_entities=sub_entities,
            wad_root=wad_root,
            wad_language=wad_language,
            events=events_data,
        )


def generate_champion_tasks(reader: DataReader, champion_ids: list[int] | None = None) -> list[tuple[str, int, str]]:
    """生成英雄任务集

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
    """生成地图任务集

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
