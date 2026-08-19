"""GUI 实体列表与映射文件的数据加载工具。"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

from loguru import logger

from lol_audio_unpack.app.artifacts import (
    AudioRef,
    enumerate_audio_refs,
)
from lol_audio_unpack.app.artifacts import (
    resolve_audio_paths as resolve_artifact_audio_paths,
)
from lol_audio_unpack.app.artifacts import (
    resolve_mapping_path as resolve_artifact_mapping_path,
)
from lol_audio_unpack.app.path_layout import get_output_dir_name
from lol_audio_unpack.app.special_content import (
    build_special_content_item,
    is_structured_special_champion,
)
from lol_audio_unpack.app.targets import (
    get_default_visible_champions,
    should_hide_champion_by_default,
)
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.errors import SharedDataMissingError
from lol_audio_unpack.manager.files import read_data
from lol_audio_unpack.model import AudioEntityData

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

GuiEntityType = Literal["champions", "maps"]


def _build_mapping_preview_base(metadata: dict[str, object] | None) -> dict[str, object]:
    """构造预览适配后的基础映射数据。"""
    return {"metadata": dict(metadata) if isinstance(metadata, dict) else {}}


def _normalize_integrated_events(events_payload: object) -> dict[str, dict[str, list[object]]]:
    """把整合版事件节点还原成预览树可消费的 mapping 结构。

    Args:
        events_payload: 整合版 ``events`` 原始节点。

    Returns:
        与普通 mapping 对齐的 ``{category: {event_name: [audio_ids]}}`` 结构。
    """
    normalized_events: dict[str, dict[str, list[object]]] = {}
    if not isinstance(events_payload, dict):
        return normalized_events

    for category, category_payload in events_payload.items():
        if not isinstance(category_payload, dict):
            continue
        mapping_payload = category_payload.get("mapping")
        if not isinstance(mapping_payload, dict):
            continue
        normalized_events[str(category)] = {
            str(event_name): list(audio_ids)
            for event_name, audio_ids in mapping_payload.items()
            if isinstance(audio_ids, list | tuple)
        }

    return normalized_events


def _normalize_integrated_audio_paths(events_payload: object) -> dict[str, dict[str, list[str]]]:
    """保留整合版事件节点中的精确 WEM 相对路径。

    Args:
        events_payload: 整合版 ``audioPaths`` 原始节点。

    Returns:
        与普通 mapping 对齐的 ``{category: {event_name: [relative_path]}}`` 结构。
    """
    normalized_paths: dict[str, dict[str, list[str]]] = {}
    if not isinstance(events_payload, dict):
        return normalized_paths

    for category, event_payload in events_payload.items():
        if not isinstance(event_payload, dict):
            continue
        paths_by_event: dict[str, list[str]] = {}
        for event_name, paths in event_payload.items():
            if not isinstance(paths, list | tuple):
                continue
            normalized = [str(path).strip() for path in paths if str(path).strip()]
            if normalized:
                paths_by_event[str(event_name)] = normalized
        if paths_by_event:
            normalized_paths[str(category)] = paths_by_event

    return normalized_paths


def _normalize_integrated_mapping_data(
    mapping_data: dict[str, object] | None,
    *,
    entity_type: GuiEntityType,
    entity_id: str,
) -> dict[str, object] | None:
    """把整合版 mapping 数据投影成当前预览页使用的普通视图。

    Args:
        mapping_data: 原始 mapping 数据。
        entity_type: GUI 实体类型目录名。
        entity_id: 当前实体 ID。

    Returns:
        若输入是整合版结构，则返回适配后的普通 mapping 视图；否则原样返回。
    """
    if not isinstance(mapping_data, dict):
        return mapping_data

    data_payload = mapping_data.get("data")
    if not isinstance(data_payload, dict):
        return mapping_data

    normalized = _build_mapping_preview_base(mapping_data.get("metadata"))

    if entity_type == "champions":
        skins_payload = data_payload.get("skins")
        if not isinstance(skins_payload, list):
            return mapping_data

        normalized["championId"] = data_payload.get("championId", entity_id)
        normalized["alias"] = data_payload.get("alias", "")
        normalized_skins: dict[str, dict[str, object]] = {}
        for skin_payload in skins_payload:
            if not isinstance(skin_payload, dict):
                continue
            skin_id = str(skin_payload.get("id", "")).strip()
            if not skin_id:
                continue

            normalized_events = _normalize_integrated_events(skin_payload.get("events"))
            normalized_paths = _normalize_integrated_audio_paths(skin_payload.get("audioPaths"))
            if normalized_events or normalized_paths:
                normalized_skin: dict[str, object] = {"events": normalized_events}
                if normalized_paths:
                    normalized_skin["audioPaths"] = normalized_paths
                normalized_skins[skin_id] = normalized_skin

        normalized["skins"] = normalized_skins
        return normalized

    map_payload = data_payload.get("map")
    if not isinstance(map_payload, dict):
        return mapping_data

    normalized["mapId"] = data_payload.get("mapId", entity_id)
    normalized["name"] = data_payload.get("name", "")
    normalized_events = _normalize_integrated_events(map_payload.get("events"))
    normalized_map: dict[str, object] = {"events": normalized_events}
    normalized_paths = _normalize_integrated_audio_paths(map_payload.get("audioPaths"))
    if normalized_paths:
        normalized_map["audioPaths"] = normalized_paths
    normalized["map"] = {str(data_payload.get("mapId", entity_id)): normalized_map}
    return normalized


def resolve_entity_audio_paths(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[Path, ...]:
    """解析实体解包后的实际输出目录。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        实际存在的音频输出目录列表。
    """
    return resolve_artifact_audio_paths(ctx, entity_data, version)


def resolve_mapping_file_path(
    ctx: AppContext,
    entity_type: GuiEntityType,
    entity_id: str,
    version: str,
) -> Path | None:
    """解析实体映射文件的实际路径。

    Args:
        ctx: 当前应用上下文。
        entity_type: GUI 使用的实体类型目录名。
        entity_id: 实体 ID。
        version: 当前数据版本号。

    Returns:
        映射文件的实际路径；不存在时返回 ``None``。
    """
    return resolve_artifact_mapping_path(
        ctx,
        entity_dir=entity_type,
        entity_id=entity_id,
        version=version,
    )


def check_entity_status(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str,
) -> tuple[str, str]:
    """检查实体的解包和映射状态。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        音频状态与映射状态组成的二元组。
    """
    audio_paths = resolve_entity_audio_paths(ctx, entity_data, version)
    audio_exists = any(path.exists() and any(path.iterdir()) for path in audio_paths)

    mapping_path = resolve_mapping_file_path(
        ctx,
        get_output_dir_name(entity_data.entity_type),
        str(entity_data.entity_id),
        version,
    )
    mapping_exists = mapping_path is not None

    return (
        "已存在" if audio_exists else "未存在",
        "已存在" if mapping_exists else "未存在",
    )


class EntityDataLoader:
    """负责从解包目录加载实体数据和映射预览。"""

    def __init__(self, app_context: AppContext):
        """初始化 GUI 数据加载器。

        Args:
            app_context: 当前应用上下文。
        """
        self.ctx = app_context
        self.data_reader = DataReader(app_context)

    def _build_entity_data(self, entity_type: GuiEntityType, entity_id: str) -> AudioEntityData:
        """按 GUI 实体类型构造对应的实体数据对象。

        Args:
            entity_type: GUI 使用的实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            对应实体的数据对象。
        """
        normalized_type = "champion" if entity_type == "champions" else "map"
        return AudioEntityData.from_entity(
            normalized_type,
            int(entity_id),
            self.data_reader,
            ctx=self.ctx,
        )

    def _load_raw_entities(self, entity_type: GuiEntityType) -> tuple[str, list[dict]]:
        """读取指定实体类型对应的原始实体列表与版本号。"""
        version = self.data_reader.version
        raw_data = (
            get_default_visible_champions(self.data_reader)
            if entity_type == "champions"
            else self.data_reader.get_maps()
        )
        return version, raw_data

    def _ensure_bank_dataset_ready(self, entity_type: GuiEntityType) -> None:
        """在按实体扫描前，先确认对应 bank 数据集根目录已经就绪。"""
        bank_root = (
            self.data_reader.champion_banks_dir if entity_type == "champions" else self.data_reader.map_banks_dir
        )
        if bank_root.is_dir():
            return

        raise SharedDataMissingError(f"{entity_type} 共享 bank 数据目录不存在，请先运行更新程序。path={bank_root}")

    def _build_entity_row(self, entity_type: GuiEntityType, entity_dict: dict, version: str) -> dict:
        """将单个原始实体字典转换为 GUI 行数据。"""
        entity_id = str(entity_dict["id"])
        entity_data = self._build_entity_data(entity_type, entity_id)

        audio_status, mapping_status = check_entity_status(self.ctx, entity_data, version)
        mapping_path = resolve_mapping_file_path(
            self.ctx,
            entity_type,
            entity_id,
            version,
        )

        if entity_data.entity_title:
            display_name = f"{entity_data.entity_name}·{entity_data.entity_title}"
        else:
            display_name = entity_data.entity_name

        return {
            "id": entity_id,
            "name": display_name,
            "alias": entity_data.entity_alias or "",
            "audio": audio_status,
            "mapping": mapping_status,
            "entity_type": entity_type,
            "mapping_file": str(mapping_path) if mapping_path else "",
        }

    def _localized_champion_name(self, champion: dict) -> str:
        """读取当前区域的英雄名，缺失时交由 special profile 回退基础 alias。"""
        names = champion.get("names", {})
        if not isinstance(names, dict):
            return ""
        return str(names.get(self.ctx.game_region, names.get("default", ""))).strip()

    def _build_special_row(self, champion: dict, version: str, *, display_name: str) -> dict | None:
        """构造特殊内容行；缺少 banks 时保留可解释的未准备状态。"""
        item = build_special_content_item(
            champion,
            display_name=display_name,
        )
        if item is None:
            return None

        audio_status = "未准备"
        mapping_status = "未准备"
        mapping_file = ""
        try:
            entity_data = self._build_entity_data("champions", str(item.champion_id))
            audio_status, mapping_status = check_entity_status(self.ctx, entity_data, version)
            mapping_path = resolve_mapping_file_path(self.ctx, "champions", str(item.champion_id), version)
            mapping_file = str(mapping_path) if mapping_path else ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("特殊内容 {} 尚未准备可用 banks，将保留在目录中: {}", item.key, exc)

        return {
            "id": str(item.champion_id),
            "key": item.key,
            "name": item.display_name,
            "display_name": item.standalone_name,
            "alias": item.internal_alias,
            "base_alias": item.base_alias,
            "mode_key": item.profile.mode_key,
            "mode_display_name": item.profile.display_name,
            "mode_english_name": item.profile.english_name,
            "search_text": item.search_text,
            "tooltip": (
                f"{item.standalone_name}\n"
                f"ID: {item.champion_id}\n"
                f"资源键: {item.key}\n"
                f"内部标识: {item.internal_alias}\n"
                f"音频: {audio_status}\n"
                f"映射: {mapping_status}\n"
                f"文件: {mapping_file or '当前还没有 mapping 文件'}"
            ),
            "audio": audio_status,
            "mapping": mapping_status,
            "entity_type": "champions",
            "mapping_file": mapping_file,
        }

    def load_champion_catalog(self) -> dict[str, list[dict]]:
        """一次读取并扫描完整英雄数据，分区返回普通与特殊目录。"""
        try:
            version = self.data_reader.version
            champions = self.data_reader.get_champions()
            self._ensure_bank_dataset_ready("champions")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"Error initializing data for champions: {exc}")
            raise

        ordinary_rows: list[dict] = []
        special_rows: list[dict] = []
        ordinary_names = {
            str(champion.get("alias", "")).casefold(): self._localized_champion_name(champion)
            for champion in champions
            if not is_structured_special_champion(champion)
        }
        for champion in champions:
            if is_structured_special_champion(champion):
                profile_item = build_special_content_item(champion)
                display_name = ordinary_names.get(profile_item.base_alias.casefold(), "") if profile_item else ""
                row = self._build_special_row(champion, version, display_name=display_name)
                if row is not None:
                    special_rows.append(row)
                continue
            if should_hide_champion_by_default(champion):
                continue
            try:
                ordinary_rows.append(self._build_entity_row("champions", champion, version))
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"Error loading entity {champion.get('id', 'unknown')}: {exc}")

        return {"champions": ordinary_rows, "special": special_rows}

    def load_champion_rows_by_targets(
        self,
        *,
        champion_ids: tuple[str, ...] = (),
        special_targets: tuple[str, ...] = (),
    ) -> dict[str, list[dict]]:
        """一次读取冠军元数据，仅重建指定普通与特殊条目的输出状态。

        Args:
            champion_ids: 要增量更新的普通英雄数值 ID。
            special_targets: 要增量更新的 ``champion:<id>`` 特殊内容 key。

        Returns:
            包含 ``champions`` 与 ``special`` 两个分区的增量行。
        """
        ordinary_targets = set(champion_ids)
        special_target_keys = set(special_targets)
        if not ordinary_targets and not special_target_keys:
            return {"champions": [], "special": []}

        try:
            version = self.data_reader.version
            champions = self.data_reader.get_champions()
            self._ensure_bank_dataset_ready("champions")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"Error initializing data for champions: {exc}")
            raise

        ordinary_names = {
            str(champion.get("alias", "")).casefold(): self._localized_champion_name(champion)
            for champion in champions
            if not is_structured_special_champion(champion)
        }
        ordinary_rows: list[dict] = []
        special_rows: list[dict] = []
        for champion in champions:
            entity_id = str(champion.get("id", ""))
            if is_structured_special_champion(champion):
                profile_item = build_special_content_item(champion)
                if profile_item is None or profile_item.key not in special_target_keys:
                    continue
                display_name = ordinary_names.get(profile_item.base_alias.casefold(), "")
                row = self._build_special_row(champion, version, display_name=display_name)
                if row is not None:
                    special_rows.append(row)
                continue

            if entity_id not in ordinary_targets or should_hide_champion_by_default(champion):
                continue
            try:
                ordinary_rows.append(self._build_entity_row("champions", champion, version))
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"Error loading entity {champion.get('id', 'unknown')}: {exc}")

        return {"champions": ordinary_rows, "special": special_rows}

    def load_entities(self, entity_type: Literal["champions", "maps"]) -> list[dict]:
        """加载指定类型的实体数据。

        Args:
            entity_type: 实体类型。

        Returns:
            供 GUI 直接展示的实体列表。
        """
        if entity_type == "champions":
            return self.load_champion_catalog()["champions"]

        try:
            version, raw_data = self._load_raw_entities(entity_type)
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as e:
            logger.opt(exception=True).warning(f"Error initializing data for {entity_type}: {e}")
            raise

        result = []
        for entity_dict in raw_data:
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.opt(exception=True).warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                continue

        return result

    def load_entities_by_ids(self, entity_type: GuiEntityType, entity_ids: tuple[str, ...]) -> list[dict]:
        """按实体 ID 增量加载指定类型的 GUI 行数据。"""
        if not entity_ids:
            return []

        target_ids = set(entity_ids)
        try:
            version, raw_data = self._load_raw_entities(entity_type)
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as e:
            logger.opt(exception=True).warning(f"Error initializing data for {entity_type}: {e}")
            raise

        result = []
        for entity_dict in raw_data:
            entity_id = str(entity_dict.get("id", ""))
            if entity_id not in target_ids:
                continue
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.opt(exception=True).warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                continue

        return result

    def load_mapping_preview(self, entity_type: GuiEntityType, entity_id: str) -> tuple[Path | None, dict | None, str]:
        """读取实体映射文件并序列化为可预览文本。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            映射文件路径、原始映射数据与序列化后的文本内容；未找到文件时返回 ``(None, None, "")``。
        """
        mapping_path = resolve_mapping_file_path(
            self.ctx,
            entity_type,
            str(entity_id),
            self.data_reader.version,
        )
        if mapping_path is None:
            return None, None, ""

        raw_mapping_data = read_data(mapping_path, dev_mode=getattr(self.ctx.config, "dev_mode", False))
        mapping_data = _normalize_integrated_mapping_data(
            raw_mapping_data,
            entity_type=entity_type,
            entity_id=str(entity_id),
        )
        return mapping_path, mapping_data, json.dumps(raw_mapping_data, ensure_ascii=False, indent=2)

    def load_audio_refs(self, entity_type: GuiEntityType, entity_id: str) -> tuple[AudioRef, ...]:
        """加载当前实体全部已解包 WEM 的路径级稳定引用。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            按相对路径排序的 WEM 引用；同一 ID 的不同路径会保留为独立项。
        """
        entity_data = self._build_entity_data(entity_type, str(entity_id))
        return enumerate_audio_refs(self.ctx, entity_data, self.data_reader.version)

    def load_audio_roots(
        self,
        entity_type: GuiEntityType,
        entity_id: str,
        *,
        audio_refs: tuple[AudioRef, ...] = (),
    ) -> tuple[Path, ...]:
        """加载当前实体实际存在的音频输出目录。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。
            audio_refs: 已枚举的路径级引用；提供时用于覆盖全部实际音频根。

        Returns:
            当前实体已存在的音频输出目录。
        """
        if audio_refs:
            roots = {root for ref in audio_refs if (root := self._resolve_audio_ref_root(ref)) is not None}
            return tuple(sorted(roots, key=lambda path: str(path).casefold()))

        entity_data = self._build_entity_data(entity_type, str(entity_id))
        return resolve_entity_audio_paths(self.ctx, entity_data, self.data_reader.version)

    def _resolve_audio_ref_root(self, ref: AudioRef) -> Path | None:
        """从路径级引用恢复其所属的实体音频根目录。"""
        parts = PurePosixPath(ref.relative_path).parts
        physical_part_count = len(parts) - (1 if self.ctx.config.group_by_type else 0)
        if physical_part_count <= 0:
            return None
        try:
            return ref.path.parents[physical_part_count - 1]
        except IndexError:
            return None
