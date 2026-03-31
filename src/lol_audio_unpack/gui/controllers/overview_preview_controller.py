"""实体总览预览加载控制器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lol_audio_unpack.gui.service.data_loader import EntityDataLoader


@dataclass(slots=True, frozen=True)
class OverviewPreviewLoadResult:
    """描述一次总览预览加载的结果。"""

    entity_id: str
    mapping_path: Path | None
    mapping_data: dict[str, Any] | None
    preview_content: str
    available_audio_ids: set[str]
    group_label_map: dict[str, str]
    placeholder_message: str | None = None


@dataclass(slots=True, frozen=True)
class AudioPreviewToggleResult:
    """描述一次试听切换后的目标状态。"""

    audio_id: str | None
    audio_path: Path | None
    progress: float
    is_playing: bool
    is_paused: bool
    warning_message: str | None = None


class OverviewPreviewController:
    """负责把实体选择转换为可渲染的预览数据。"""

    def load_preview(
        self,
        *,
        entity_type: str,
        entity_id: str,
        entity_name: str,
        loader: EntityDataLoader | None,
    ) -> OverviewPreviewLoadResult:
        """加载指定实体的预览结果。"""
        if loader is None:
            return OverviewPreviewLoadResult(
                entity_id=entity_id,
                mapping_path=None,
                mapping_data=None,
                preview_content="",
                available_audio_ids=set(),
                group_label_map={},
                placeholder_message="当前配置尚未完成初始化，暂时无法读取预览内容。",
            )

        mapping_path, mapping_data, preview_content = loader.load_mapping_preview(entity_type, entity_id)
        if mapping_path is None:
            return OverviewPreviewLoadResult(
                entity_id=entity_id,
                mapping_path=None,
                mapping_data=None,
                preview_content="",
                available_audio_ids=set(),
                group_label_map={},
                placeholder_message=f"{entity_name} 当前还没有映射文件。",
            )

        available_audio_ids = loader.load_available_audio_ids(entity_type, entity_id)
        group_label_map = self._build_preview_group_label_map(
            entity_type=entity_type,
            entity_id=entity_id,
            mapping_data=mapping_data,
            loader=loader,
        )
        return OverviewPreviewLoadResult(
            entity_id=entity_id,
            mapping_path=mapping_path,
            mapping_data=mapping_data,
            preview_content=preview_content or "{}",
            available_audio_ids=available_audio_ids,
            group_label_map=group_label_map,
        )

    def _build_preview_group_label_map(
        self,
        *,
        entity_type: str,
        entity_id: str,
        mapping_data: dict[str, Any] | None,
        loader: EntityDataLoader,
    ) -> dict[str, str]:
        """为试听树构造首层分组展示文案映射。"""
        if entity_type != "champions":
            return {}
        if not isinstance(mapping_data, dict) or not isinstance(mapping_data.get("skins"), dict):
            return {}

        try:
            champion_id = int(entity_id)
        except (TypeError, ValueError):
            return {}

        champion = loader.data_reader.get_champion(champion_id)
        if not isinstance(champion, dict):
            return {}

        label_map: dict[str, str] = {}
        for skin in champion.get("skins", []):
            if not isinstance(skin, dict):
                continue

            skin_id = str(skin.get("id") or "").strip()
            if not skin_id:
                continue

            skin_name = self._resolve_champion_skin_name(skin)
            if skin_name:
                label_map[skin_id] = skin_name

        return label_map

    def resolve_audio_preview_toggle(
        self,
        *,
        requested_audio_id: str,
        current_audio_id: str | None,
        loader: EntityDataLoader | None,
        current_entity_type: str | None,
        current_entity_id: str | None,
    ) -> AudioPreviewToggleResult | None:
        """根据当前试听状态解析下一步播放请求。"""
        if requested_audio_id == current_audio_id:
            return AudioPreviewToggleResult(
                audio_id=None,
                audio_path=None,
                progress=0.0,
                is_playing=False,
                is_paused=False,
            )

        if (
            loader is None
            or current_entity_type is None
            or current_entity_id is None
        ):
            return None

        audio_path = loader.resolve_audio_file_path(
            current_entity_type,
            current_entity_id,
            requested_audio_id,
        )
        if audio_path is None:
            return AudioPreviewToggleResult(
                audio_id=None,
                audio_path=None,
                progress=0.0,
                is_playing=False,
                is_paused=False,
                warning_message=f"当前实体未定位到音频 ID {requested_audio_id} 对应的 wem 文件。",
            )

        return AudioPreviewToggleResult(
            audio_id=str(requested_audio_id),
            audio_path=audio_path,
            progress=0.0,
            is_playing=False,
            is_paused=True,
        )

    @staticmethod
    def _resolve_champion_skin_name(skin: dict[str, Any]) -> str | None:
        """从英雄皮肤结构中提取可展示的皮肤名。"""
        skin_names = skin.get("skinNames")
        if isinstance(skin_names, dict):
            zh_name = str(skin_names.get("zh_CN") or "").strip()
            if zh_name:
                return zh_name

        for key in ("name", "displayName"):
            value = str(skin.get(key) or "").strip()
            if value:
                return value

        return None
