"""共享音频实体定义。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lol_audio_unpack.app.resource_pack import RESOURCE_PACK_ENTITY_TYPE, parse_resource_pack_key
from lol_audio_unpack.app.types import SourceMode
from lol_audio_unpack.model.binding import BankBinding, BindingDiagnostics
from lol_audio_unpack.utils.common import sanitize_filename

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext
    from lol_audio_unpack.manager.data_reader import DataReader


@dataclass
class AudioBank:
    """面向消费者的 bank binding 投影。

    Args:
        sub_id: bank 所属的逻辑子实体 ID。
        audio_type: 由分类推导出的音频类型。
        binding: P1 产生的原始 resource binding。
    """

    sub_id: str
    audio_type: str
    binding: BankBinding


@dataclass
class AudioEntityData:
    """统一描述可解包和可映射的音频实体。

    Args:
        entity_id: 实体 ID，例如英雄 ID、地图 ID 或 resource-pack key。
        entity_name: 实体名称。
        entity_alias: 实体别名。
        entity_title: 实体标题；无标题时为 ``None``。
        entity_type: 实体类型，支持 ``"champion"``、``"map"`` 或 ``"resource_pack"``。
        sub_entities: 子实体数据，例如皮肤或地图自身。
        wad_root: 根 WAD 相对路径，用于 SFX/MUSIC。
        wad_language: 语言 WAD 相对路径，用于 VO；缺失时为 ``None``。
        events: 事件数据，仅映射流程需要；缺失时为 ``None``。
        resource_banks: local v2 使用的逐条 bank binding 消费投影。
        binding_diagnostics: local v2 artifact 的 binding 诊断；remote v1 为 ``None``。
    """

    entity_id: str
    entity_name: str
    entity_alias: str
    entity_title: str | None
    entity_type: str  # "champion" | "map" | "resource_pack"
    sub_entities: dict[str, dict[str, Any]]
    wad_root: str
    wad_language: str | None = None
    events: dict[str, dict[str, Any]] | None = None
    resource_banks: tuple[AudioBank, ...] = ()
    binding_diagnostics: BindingDiagnostics | None = None

    def get_sub_entity_info(self, sub_id: str) -> dict[str, Any] | None:
        """返回子实体的基础信息。

        Args:
            sub_id: 子实体 ID，例如皮肤 ID 或地图 ID。

        Returns:
            dict[str, Any] | None: 包含 ``id`` 与 ``name`` 的字典；不存在时返回 ``None``。
        """
        sub_entity = self.sub_entities.get(sub_id)
        if not sub_entity:
            return None

        sub_entity_id: int | str = sub_id if self.entity_type == RESOURCE_PACK_ENTITY_TYPE else int(sub_id)
        return {"id": sub_entity_id, "name": sub_entity["name"]}

    def get_wad_path(
        self,
        audio_type: str,
        *,
        ctx: AppContext,
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
    def from_entity(
        cls,
        entity_type: str,
        entity_id: int | str,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: AppContext,
    ) -> AudioEntityData:
        """按实体类型构建统一的音频实体。

        Args:
            entity_type: 实体类型，支持 ``"champion"``、``"map"`` 或 ``"resource_pack"``。
            entity_id: 实体 ID。
            reader: 数据读取器实例。
            include_events: 是否附带事件数据。
            ctx: 运行时上下文。

        Returns:
            AudioEntityData: 对应实体的音频实体。

        Raises:
            ValueError: 当实体类型未知或底层实体构建失败时抛出。
        """
        if entity_type == "champion":
            return cls.from_champion(
                entity_id,
                reader,
                include_events=include_events,
                ctx=ctx,
            )
        if entity_type == "map":
            return cls.from_map(
                entity_id,
                reader,
                include_events=include_events,
                ctx=ctx,
            )
        if entity_type == RESOURCE_PACK_ENTITY_TYPE:
            return cls.from_resource_pack(
                str(entity_id),
                reader,
                include_events=include_events,
                ctx=ctx,
            )
        raise ValueError(f"未知的实体类型: {entity_type}")

    @classmethod
    def from_champion(
        cls,
        champion_id: int,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: AppContext,
    ) -> AudioEntityData:
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

        resource_bindings = reader.get_champion_resource_bindings(champion_id) if _uses_local_bindings(ctx) else None
        champion_banks = None if resource_bindings is not None else reader.get_champion_banks(champion_id)
        if resource_bindings is None and not champion_banks:
            if _uses_local_bindings(ctx):
                raise ValueError(f"英雄ID {champion_id} 缺少 resource schema v2，请先重新运行 update")
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

        sub_entities: dict[str, dict[str, Any]] = {}
        available_skins = champion_banks.get("skins", {}) if champion_banks else {}

        for skin_id_str, banks in available_skins.items():
            skin_info = skin_info_map.get(skin_id_str)
            if not skin_info:
                continue

            # 这里只保留当前 banks 真正出现的皮肤，
            # 避免后续流程再为“有皮肤定义但没有音频数据”的空壳子实体兜底。
            sub_entities[skin_id_str] = {"name": skin_info["name"], "categories": banks}

        resource_banks = _build_audio_banks(resource_bindings, reader) if resource_bindings is not None else ()
        if resource_bindings is not None:
            for bank in resource_banks:
                skin_info = skin_info_map.get(bank.sub_id)
                if skin_info is not None:
                    sub_entities.setdefault(bank.sub_id, {"name": skin_info["name"], "categories": {}})

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
            resource_banks=resource_banks,
            binding_diagnostics=resource_bindings.diagnostics if resource_bindings is not None else None,
        )

    @classmethod
    def from_map(
        cls,
        map_id: int,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: AppContext,
    ) -> AudioEntityData:
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

        resource_bindings = reader.get_map_resource_bindings(map_id) if _uses_local_bindings(ctx) else None
        map_banks = None if resource_bindings is not None else reader.get_map_banks(map_id)
        if resource_bindings is None and not map_banks:
            if _uses_local_bindings(ctx):
                raise ValueError(f"地图ID {map_id} 缺少 resource schema v2，请先重新运行 update")
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
        sub_entities = {
            str(map_id): {"name": safe_map_name, "categories": map_banks.get("banks", {}) if map_banks else {}}
        }
        resource_banks = _build_audio_banks(resource_bindings, reader) if resource_bindings is not None else ()

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
            resource_banks=resource_banks,
            binding_diagnostics=resource_bindings.diagnostics if resource_bindings is not None else None,
        )

    @classmethod
    def from_resource_pack(
        cls,
        key: str,
        reader: DataReader,
        include_events: bool = False,
        *,
        ctx: AppContext,
    ) -> AudioEntityData:
        """从 resource-pack v2 artifact 构建唯一逻辑子实体。

        Args:
            key: canonical ``resource_pack:...`` 稳定 key。
            reader: 数据读取器实例。
            include_events: 是否附带 resource-pack events。
            ctx: 运行时上下文。

        Returns:
            带完整 string identity、绑定投影与可选事件的音频实体。

        Raises:
            ValueError: 当前不是 local v2、artifact 不完整或 metadata 与 key 不一致时抛出。
        """
        if not _uses_local_bindings(ctx):
            raise ValueError("resource pack 仅支持本地 resource schema v2")
        parse_resource_pack_key(key)
        resource_bindings = reader.get_resource_pack_resource_bindings(key)
        banks_data = reader.get_resource_pack_banks(key, require_bindings=True)
        if resource_bindings is None or banks_data is None:
            raise ValueError(f"资源包 {key} 缺少 resource schema v2，请先重新运行 update")
        if resource_bindings.entity_type != RESOURCE_PACK_ENTITY_TYPE or resource_bindings.entity_id != key:
            raise ValueError(f"资源包 {key} 的 binding identity 无效")

        resource_pack = banks_data.get("resourcePack")
        if not isinstance(resource_pack, dict) or resource_pack.get("key") != key:
            raise ValueError(f"资源包 {key} 的 metadata 无效")
        namespace = resource_pack.get("namespace")
        wad_root = resource_pack.get("wad")
        if not isinstance(namespace, str) or not namespace.strip() or not isinstance(wad_root, str) or not wad_root:
            raise ValueError(f"资源包 {key} 缺少 namespace 或来源 WAD metadata")

        # 资源包没有皮肤/地图层级；key 本身作为唯一逻辑子实体，物理 WAD 仍完全由 binding 决定。
        display_name = sanitize_filename(namespace.replace("_", " "))
        entity_alias = sanitize_filename(namespace.casefold())
        resource_banks = _build_audio_banks(resource_bindings, reader)
        events_data = None
        if include_events:
            events_payload = reader.get_resource_pack_events(key)
            events = events_payload.get("events", {}) if events_payload else {}
            events_data = {key: {"events": events}}

        return cls(
            entity_id=key,
            entity_name=display_name,
            entity_alias=entity_alias,
            entity_title=None,
            entity_type=RESOURCE_PACK_ENTITY_TYPE,
            sub_entities={key: {"name": display_name, "categories": banks_data.get("banks", {})}},
            wad_root=wad_root,
            events=events_data,
            resource_banks=resource_banks,
            binding_diagnostics=resource_bindings.diagnostics,
        )


def _uses_local_bindings(ctx: AppContext) -> bool:
    """判断当前实体工厂是否必须消费 local v2 bindings。"""
    mode = getattr(ctx.config, "source_mode", SourceMode.LOCAL_PATH)
    return mode in {SourceMode.LOCAL_PATH, SourceMode.LOCAL_PATH.value}


def _build_audio_banks(resource_bindings: Any, reader: DataReader) -> tuple[AudioBank, ...]:
    """从 typed bindings 构建不改写 P1 合同的消费者投影。"""
    return tuple(
        AudioBank(
            sub_id=binding.sub_entity or resource_bindings.entity_id,
            audio_type=reader.get_audio_type(binding.category),
            binding=binding,
        )
        for binding in resource_bindings.bank_bindings
    )


__all__ = ["AudioBank", "AudioEntityData"]
