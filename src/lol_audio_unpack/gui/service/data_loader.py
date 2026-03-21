"""GUI 实体列表与映射文件的数据加载工具。"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from loguru import logger

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext

from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.utils import find_data_file, read_data
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.utils.path_constants import format_entity_folder_name, get_output_dir_name

GuiEntityType = Literal["champions", "maps"]


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
    hash_dir = Path(ctx.paths.hash_path) / version / entity_type
    return find_data_file(hash_dir / str(entity_id), dev_mode=getattr(ctx.config, "dev_mode", False))


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

    def load_entities(self, entity_type: Literal["champions", "maps"]) -> list[dict]:
        """加载指定类型的实体数据。

        Args:
            entity_type: 实体类型。

        Returns:
            供 GUI 直接展示的实体列表。
        """
        try:
            version = self.data_reader.version
            raw_data = self.data_reader.get_champions() if entity_type == "champions" else self.data_reader.get_maps()
        except Exception as e:
            logger.warning(f"Error initializing data for {entity_type}: {e}")
            logger.debug(traceback.format_exc())
            return []

        result = []
        for entity_dict in raw_data:
            try:
                entity_id = str(entity_dict["id"])

                if entity_type == "champions":
                    entity_data = AudioEntityData.from_champion(
                        int(entity_id), self.data_reader, ctx=self.ctx
                    )
                else:
                    entity_data = AudioEntityData.from_map(
                        int(entity_id), self.data_reader, ctx=self.ctx
                    )

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

                result.append({
                    "id": entity_id,
                    "name": display_name,
                    "alias": entity_data.entity_alias or "",
                    "audio": audio_status,
                    "mapping": mapping_status,
                    "entity_type": entity_type,
                    "mapping_file": str(mapping_path) if mapping_path else "",
                })
            except Exception as e:
                logger.warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                logger.debug(traceback.format_exc())
                continue

        return result

    def load_mapping_preview(self, entity_type: GuiEntityType, entity_id: str) -> tuple[Path | None, str]:
        """读取实体映射文件并序列化为可预览文本。

        Args:
            entity_type: 实体类型目录名。
            entity_id: 实体 ID。

        Returns:
            映射文件路径与序列化后的文本内容；未找到文件时返回 ``(None, "")``。
        """
        mapping_path = resolve_mapping_file_path(
            self.ctx,
            entity_type,
            str(entity_id),
            self.data_reader.version,
        )
        if mapping_path is None:
            return None, ""

        mapping_data = read_data(mapping_path, dev_mode=getattr(self.ctx.config, "dev_mode", False))
        return mapping_path, json.dumps(mapping_data, ensure_ascii=False, indent=2)
