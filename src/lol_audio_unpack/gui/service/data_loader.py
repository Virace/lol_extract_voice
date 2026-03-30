"""GUI 实体列表与映射文件的数据加载工具。"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext

from lol_audio_unpack.manager.data_reader import DataReader, get_default_visible_champions
from lol_audio_unpack.manager.utils import find_data_file, read_data
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.utils.path_constants import format_entity_folder_name, get_output_dir_name

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
        normalized_skins: dict[str, dict[str, dict[str, list[object]]]] = {}
        for skin_payload in skins_payload:
            if not isinstance(skin_payload, dict):
                continue
            skin_id = str(skin_payload.get("id", "")).strip()
            if not skin_id:
                continue

            normalized_events = _normalize_integrated_events(skin_payload.get("events"))
            if normalized_events:
                normalized_skins[skin_id] = {"events": normalized_events}

        normalized["skins"] = normalized_skins
        return normalized

    map_payload = data_payload.get("map")
    if not isinstance(map_payload, dict):
        return mapping_data

    normalized["mapId"] = data_payload.get("mapId", entity_id)
    normalized["name"] = data_payload.get("name", "")
    normalized_events = _normalize_integrated_events(map_payload.get("events"))
    normalized["map"] = {
        str(data_payload.get("mapId", entity_id)): {"events": normalized_events}
    }
    return normalized


def resolve_entity_audio_paths(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str
) -> tuple[Path, ...]:
    """解析实体解包后的实际输出目录。

    Args:
        ctx: 当前应用上下文。
        entity_data: 实体数据对象。
        version: 当前数据版本号。

    Returns:
        实际存在的音频输出目录列表。
    """
    audio_base = Path(ctx.paths.audio_path)
    entity_dir = get_output_dir_name(entity_data.entity_type)
    entity_folder_name = format_entity_folder_name(
        entity_data.entity_id,
        entity_data.entity_alias,
        entity_data.entity_name,
        entity_data.entity_title,
    )
    version_audio_root = audio_base / version

    if ctx.config.group_by_type:
        paths = tuple(
            candidate
            for audio_type in ctx.config.include_types
            if (candidate := version_audio_root / audio_type / entity_dir / entity_folder_name).exists()
        )
        return paths

    candidate = version_audio_root / entity_dir / entity_folder_name
    if candidate.exists():
        return (candidate,)
    return ()


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
    hash_root = Path(ctx.paths.hash_path) / version
    dev_mode = getattr(ctx.config, "dev_mode", False)

    integrated_path = find_data_file(
        hash_root / "integrated" / entity_type / str(entity_id),
        dev_mode=dev_mode,
    )
    if integrated_path is not None:
        return integrated_path

    return find_data_file(
        hash_root / entity_type / str(entity_id),
        dev_mode=dev_mode,
    )


def check_entity_status(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str
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
    audio_exists = any(
        path.exists() and any(path.iterdir())
        for path in audio_paths
    )

    mapping_path = resolve_mapping_file_path(
        ctx,
        get_output_dir_name(entity_data.entity_type),
        str(entity_data.entity_id),
        version,
    )
    mapping_exists = mapping_path is not None

    return (
        "已存在" if audio_exists else "未存在",
        "已存在" if mapping_exists else "未存在"
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
        if entity_type == "champions":
            return AudioEntityData.from_champion(int(entity_id), self.data_reader, ctx=self.ctx)

        return AudioEntityData.from_map(int(entity_id), self.data_reader, ctx=self.ctx)

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
            self.data_reader.champion_banks_dir
            if entity_type == "champions"
            else self.data_reader.map_banks_dir
        )
        if bank_root.is_dir():
            return

        raise FileNotFoundError(
            f"{entity_type} 共享 bank 数据目录不存在，请先运行更新程序。path={bank_root}"
        )

    def _build_entity_row(self, entity_type: GuiEntityType, entity_dict: dict, version: str) -> dict:
        """将单个原始实体字典转换为 GUI 行数据。"""
        entity_id = str(entity_dict["id"])
        entity_data = self._build_entity_data(entity_type, entity_id)

        audio_status, mapping_status = check_entity_status(
            self.ctx, entity_data, version
        )
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

    def load_entities(self, entity_type: Literal["champions", "maps"]) -> list[dict]:
        """加载指定类型的实体数据。

        Args:
            entity_type: 实体类型。

        Returns:
            供 GUI 直接展示的实体列表。
        """
        try:
            version, raw_data = self._load_raw_entities(entity_type)
            self._ensure_bank_dataset_ready(entity_type)
        except Exception as e:
            logger.warning(f"Error initializing data for {entity_type}: {e}")
            logger.debug(traceback.format_exc())
            raise

        result = []
        for entity_dict in raw_data:
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                logger.debug(traceback.format_exc())
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
            logger.warning(f"Error initializing data for {entity_type}: {e}")
            logger.debug(traceback.format_exc())
            raise

        result = []
        for entity_dict in raw_data:
            entity_id = str(entity_dict.get("id", ""))
            if entity_id not in target_ids:
                continue
            try:
                result.append(self._build_entity_row(entity_type, entity_dict, version))
            except Exception as e:
                logger.warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                logger.debug(traceback.format_exc())
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

    def load_available_audio_ids(self, entity_type: GuiEntityType, entity_id: str) -> set[str]:
        """加载当前实体在本地已存在的音频 ID 集合。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            当前实体输出目录下已存在的 ``.wem`` 文件 stem 集合。
        """
        entity_data = self._build_entity_data(entity_type, str(entity_id))
        audio_paths = resolve_entity_audio_paths(self.ctx, entity_data, self.data_reader.version)
        available_ids: set[str] = set()

        for audio_path in audio_paths:
            if not audio_path.exists():
                continue

            for wem_path in audio_path.rglob("*.wem"):
                available_ids.add(wem_path.stem)

        return available_ids

    def resolve_audio_file_path(self, entity_type: GuiEntityType, entity_id: str, audio_id: str) -> Path | None:
        """解析指定音频 ID 在本地输出目录中的 wem 路径。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。
            audio_id: 目标音频 ID。

        Returns:
            Path | None: 若命中本地 wem 文件则返回其路径，否则返回 ``None``。
        """
        audio_id_text = str(audio_id).strip()
        if not audio_id_text:
            return None

        entity_data = self._build_entity_data(entity_type, str(entity_id))
        audio_paths = resolve_entity_audio_paths(self.ctx, entity_data, self.data_reader.version)
        matched_paths: list[Path] = []

        for audio_path in audio_paths:
            if not audio_path.exists():
                continue

            matched_paths.extend(sorted(audio_path.rglob(f"{audio_id_text}.wem")))

        if not matched_paths:
            return None
        return min(matched_paths, key=lambda path: str(path).lower())
