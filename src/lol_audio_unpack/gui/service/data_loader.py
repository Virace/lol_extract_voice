from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext
    from lol_audio_unpack.model import AudioEntityData

from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.utils.path_constants import format_entity_folder_name, get_output_dir_name


def resolve_entity_audio_paths(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str
) -> tuple[Path, ...]:
    """解析实体解包后的实际输出目录（支持 group_by_type）"""
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


def check_entity_status(
    ctx: AppContext,
    entity_data: AudioEntityData,
    version: str
) -> tuple[str, str]:
    """检查实体的解包和映射状态"""
    audio_paths = resolve_entity_audio_paths(ctx, entity_data, version)
    audio_exists = any(
        path.exists() and any(path.iterdir())
        for path in audio_paths
    )

    hash_dir = ctx.paths.hash_path / version / get_output_dir_name(entity_data.entity_type)
    mapping_exists = any([
        (hash_dir / f"{entity_data.entity_id}.json").exists(),
        (hash_dir / f"{entity_data.entity_id}.yaml").exists(),
        (hash_dir / f"{entity_data.entity_id}.yml").exists(),
        (hash_dir / f"{entity_data.entity_id}.msgpack").exists(),
    ])

    return (
        "已存在" if audio_exists else "未存在",
        "已存在" if mapping_exists else "未存在"
    )


class EntityDataLoader:
    """负责从解包目录加载实体数据和状态"""

    def __init__(self, app_context: AppContext):
        self.ctx = app_context
        self.data_reader = DataReader(app_context)

    def load_entities(self, entity_type: Literal["champions", "maps"]) -> list[dict]:
        """加载指定类型的实体数据"""
        try:
            version = self.data_reader.version
            raw_data = self.data_reader.get_champions() if entity_type == "champions" else self.data_reader.get_maps()
        except Exception as e:
            from loguru import logger
            logger.warning(f"Error initializing data for {entity_type}: {e}")
            import traceback
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

                if entity_data.entity_title:
                    display_name = f"{entity_data.entity_name}·{entity_data.entity_title}"
                else:
                    display_name = entity_data.entity_name

                result.append({
                    "id": entity_id,
                    "name": display_name,
                    "alias": entity_data.entity_alias,
                    "audio": audio_status,
                    "mapping": mapping_status
                })
            except Exception as e:
                from loguru import logger
                logger.warning(f"Error loading entity {entity_dict.get('id', 'unknown')}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                continue

        return result
