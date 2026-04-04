"""共享音频实体模型与任务生成逻辑。"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.manager.data_reader import get_default_visible_champions
from lol_audio_unpack.utils.common import sanitize_filename

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


@dataclass
class AudioEntityData:
    """统一描述可解包和可映射的音频实体。

    Args:
        entity_id: 实体 ID，例如英雄 ID 或地图 ID。
        entity_name: 实体名称。
        entity_alias: 实体别名。
        entity_title: 实体标题；无标题时为 ``None``。
        entity_type: 实体类型，当前为 ``"champion"`` 或 ``"map"``。
        sub_entities: 子实体数据，例如皮肤或地图自身。
        wad_root: 根 WAD 相对路径，用于 SFX/MUSIC。
        wad_language: 语言 WAD 相对路径，用于 VO；缺失时为 ``None``。
        events: 事件数据，仅映射流程需要；缺失时为 ``None``。
    """

    entity_id: str
    entity_name: str
    entity_alias: str
    entity_title: str | None
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
        *,
        ctx: "AppContext",
    ) -> Path | None:
        """根据音频类型返回可用的 WAD 绝对路径。

        Args:
            audio_type: 音频类型；``"VO"`` 使用语言 WAD，其余类型使用根 WAD。
            ctx: 运行时上下文。

        Returns:
            Path | None: 存在的 WAD 绝对路径；不可用时返回 ``None``。
        """
        # VO 必须优先走语言 WAD，其他类型统一走根 WAD。
        # 这条规则由模型层集中维护，避免 mapping / unpack 各自复制分支。
        if audio_type == "VO":
            relative_path = self.wad_language
        else:
            relative_path = self.wad_root

        if not relative_path:
            return None

        # 调用方统一把 None 视为“当前音频类型没有可用 WAD”，
        # 因此这里顺手完成存在性校验，避免上层重复拼路径和判断。
        full_path = ctx.game_path / relative_path
        return full_path if full_path.exists() else None

    @classmethod
    def from_champion(
        cls,
        champion_id: int,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: "AppContext",
    ) -> "AudioEntityData":
        """从英雄数据构建音频实体。

        Args:
            champion_id: 英雄 ID。
            reader: 数据读取器实例。
            include_events: 是否附带事件数据。
            ctx: 运行时上下文。

        Returns:
            AudioEntityData: 对应英雄的音频实体。

        Raises:
            ValueError: 英雄不存在、没有音频数据或缺少根 WAD 时抛出。
        """
        champion = reader.get_champion(champion_id)
        if not champion:
            raise ValueError(f"数据中不存在英雄ID {champion_id}")

        champion_banks = reader.get_champion_banks(champion_id)
        if not champion_banks:
            raise ValueError(f"英雄ID {champion_id} 没有音频数据")

        wad_info = champion.get("wad", {})
        wad_root = wad_info.get("root")
        if not wad_root:
            raise ValueError(f"英雄ID {champion_id} 缺少根WAD文件信息")

        # AppContext 已负责标准化语言区域；模型层只消费标准化结果，
        # 不再在 champion / map / mapping / unpack 各自做 fallback。
        language = ctx.game_region
        wad_language = wad_info.get(language)

        skin_info_map = {}
        for skin in champion.get("skins", []):
            skin_id = skin.get("id")
            skin_id_str = str(skin_id)
            skin_name_raw = skin.get("skinNames", {}).get(language, skin.get("skinNames", {}).get("default", ""))
            is_base_skin = skin.get("isBase", False)
            skin_name = "基础皮肤" if is_base_skin else skin_name_raw
            # 子实体名称在模型层就完成文件名安全化，
            # 后续 unpack / mapping / GUI 都直接复用同一份稳定值。
            safe_skin_name = sanitize_filename(skin_name)
            skin_info_map[skin_id_str] = {"id": skin_id, "name": safe_skin_name}

        sub_entities = {}
        available_skins = champion_banks.get("skins", {})

        for skin_id_str, banks in available_skins.items():
            skin_info = skin_info_map.get(skin_id_str)
            if not skin_info:
                continue

            # 这里只保留当前 banks 真正出现的皮肤，
            # 避免后续流程再为“有皮肤定义但没有音频数据”的空壳子实体兜底。
            sub_entities[skin_id_str] = {"name": skin_info["name"], "categories": banks}

        events_data = None
        if include_events:
            # 解包流程不需要 events；保持按需装载，避免把 mapping 负担带进通用实体模型。
            champion_events = reader.get_champion_events(champion_id)
            events_data = champion_events.get("skins", {}) if champion_events else {}

        champion_name_raw = champion.get("names", {}).get(language, champion.get("names", {}).get("default", ""))
        safe_champion_name = sanitize_filename(champion_name_raw)
        safe_champion_alias = sanitize_filename(champion.get("alias", "").lower())

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
        ctx: "AppContext",
    ) -> "AudioEntityData":
        """从地图数据构建音频实体。

        Args:
            map_id: 地图 ID。
            reader: 数据读取器实例。
            include_events: 是否附带事件数据。
            ctx: 运行时上下文。

        Returns:
            AudioEntityData: 对应地图的音频实体。

        Raises:
            ValueError: 地图不存在、没有音频数据或缺少根 WAD 时抛出。
        """
        map_info = reader.get_map(map_id)
        if not map_info:
            raise ValueError(f"数据中不存在地图ID {map_id}")

        map_banks = reader.get_map_banks(map_id)
        if not map_banks:
            raise ValueError(f"地图ID {map_id} 没有音频数据")

        wad_info = map_info.get("wad", {})
        wad_root = wad_info.get("root")
        if not wad_root:
            raise ValueError(f"地图ID {map_id} 缺少根WAD文件信息")

        # 地图和英雄共用同一条语言选择主线，避免两边在 region 语义上再次漂移。
        language = ctx.game_region
        wad_language = wad_info.get(language)

        map_name_raw = map_info.get("names", {}).get(language, map_info.get("names", {}).get("default", ""))
        safe_map_name = sanitize_filename(map_name_raw)

        map_alias_raw = "common" if map_id == 0 else map_info.get("mapStringId", "").lower()
        safe_map_alias = sanitize_filename(map_alias_raw)

        # 地图没有独立皮肤概念，但解包和映射都按“实体 -> 子实体”统一处理，
        # 因此这里把地图包装成唯一一个子实体，减少下游分支。
        sub_entities = {str(map_id): {"name": safe_map_name, "categories": map_banks.get("banks", {})}}

        events_data = None
        if include_events:
            map_events_data = reader.get_map_events(map_id)
            # 地图事件原始结构与英雄不同，这里先整理成与皮肤一致的形状，
            # 让 mapping 主流程不必再判断“当前是 champion 还是 map”。
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
    all_champions = reader.get_champions()
    available_ids = {champ.get("id") for champ in all_champions if champ.get("id") is not None}

    if champion_ids is None:
        # 处理所有英雄
        return [
            ("champion", champ.get("id"), f"英雄ID {champ.get('id')}")
            for champ in get_default_visible_champions(reader)
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


