"""大厅 BP 音频附加逻辑。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from lol_audio_unpack.app.path_layout import format_entity_folder_name, get_output_dir_name
from lol_audio_unpack.manager import DataReader
from lol_audio_unpack.model import AudioEntityData

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

LOBBY_AUDIO_FILE_MAPPING = {
    "champion-ban-vo": "ban.ogg",
    "champion-choose-vo": "choose.ogg",
    "champion-sfx-audios": "sfx.ogg",
}


def find_bp_vo_source(
    reader: DataReader,
    champion_id: str,
    category: str,
    *,
    ctx: AppContext,
) -> Path | None:
    """查找大厅音频源文件。

    Args:
        reader: 数据读取器。
        champion_id: 英雄 ID。
        category: 大厅语音分类。
        ctx: 运行时上下文。

    Returns:
        命中的语音文件路径；未找到时返回 ``None``。
    """
    manifest_root = Path(ctx.paths.manifest_path) / reader.version / "lobby"
    region = str(ctx.config.game_region or "zh_CN")
    region_candidates: list[str] = []

    if region:
        region_candidates.append(region)
        region_lower = region.lower()
        if region_lower not in region_candidates:
            region_candidates.append(region_lower)
    if "default" not in region_candidates:
        region_candidates.append("default")

    for region_name in region_candidates:
        candidate = manifest_root / region_name / category / f"{champion_id}.ogg"
        if candidate.exists():
            return candidate

    return None


def link_or_copy(source: Path, target: Path) -> str:
    """优先创建硬链接，失败时回退为复制。

    Args:
        source: 源文件路径。
        target: 目标文件路径。

    Returns:
        实际写入模式，可能为 ``hardlink`` 或 ``copy``。
    """
    if target.exists():
        target.unlink()

    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def attach_bp_vo(
    entity: AudioEntityData,
    reader: DataReader,
    *,
    ctx: AppContext,
) -> None:
    """将大厅音频附加到英雄输出目录。

    Args:
        entity: 英雄实体数据。
        reader: 数据读取器。
        ctx: 运行时上下文。
    """
    if not bool(ctx.config.with_bp_vo):
        return

    audio_root = Path(ctx.paths.audio_path)
    entity_folder = format_entity_folder_name(
        entity.entity_id,
        entity.entity_alias,
        entity.entity_name,
        entity.entity_title,
    )

    target_dir = _build_lobby_dir(
        audio_root=audio_root,
        version=reader.version,
        entity_type=entity.entity_type,
        entity_folder=entity_folder,
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    for category, target_name in LOBBY_AUDIO_FILE_MAPPING.items():
        source = find_bp_vo_source(reader, entity.entity_id, category, ctx=ctx)
        if source is None:
            logger.warning(
                f"未找到英雄 {entity.entity_id} 的大厅音频文件: {category}/{entity.entity_id}.ogg；"
                "如当前任务未执行更新，manifest lobby 目录不会自动刷新。"
            )
            continue

        target = target_dir / target_name
        mode = link_or_copy(source, target)
        logger.debug(f"大厅音频已写入: {target} (mode={mode})")


def _build_lobby_dir(
    *,
    audio_root: Path,
    version: str,
    entity_type: str,
    entity_folder: str,
) -> Path:
    """构建统一大厅音频输出目录。"""
    return audio_root / version / get_output_dir_name(entity_type) / entity_folder / "lobby"
