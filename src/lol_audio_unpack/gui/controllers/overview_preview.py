"""实体总览预览加载控制器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader

EVENT_PREVIEW_MODE = "audio"
ALL_AUDIO_PREVIEW_MODE = "all_audio"
RAW_PREVIEW_MODE = "raw"


@dataclass(slots=True, frozen=True)
class OverviewPreviewLoadResult:
    """描述一次总览预览加载的结果。"""

    entity_id: str
    mapping_path: Path | None
    mapping_data: dict[str, Any] | None
    preview_content: str
    available_audio_ids: set[str]
    group_label_map: dict[str, str]
    audio_refs: tuple[AudioRef, ...] = ()
    audio_roots: tuple[Path, ...] = ()
    default_preview_mode: str = ALL_AUDIO_PREVIEW_MODE
    mapping_notice: str | None = None
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
        audio_refs = loader.load_audio_refs(entity_type, entity_id)
        audio_roots = loader.load_audio_roots(entity_type, entity_id, audio_refs=audio_refs)
        available_audio_ids = {ref.wem_id for ref in audio_refs}
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
            preview_content=preview_content or "尚未生成事件映射。",
            available_audio_ids=available_audio_ids,
            group_label_map=group_label_map,
            audio_refs=audio_refs,
            audio_roots=audio_roots,
            default_preview_mode=EVENT_PREVIEW_MODE if mapping_path is not None else ALL_AUDIO_PREVIEW_MODE,
            mapping_notice=None if mapping_path is not None else f"{entity_name} 尚未生成事件映射。",
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
        requested_audio: AudioRef,
        current_audio_path: Path | None,
    ) -> AudioPreviewToggleResult | None:
        """根据精确 WEM 引用解析下一步试听请求。

        Args:
            requested_audio: 用户实际点击的路径级 WEM 引用。
            current_audio_path: 当前播放器正在管理的精确 WEM 路径。

        Returns:
            新的播放或停止状态。
        """
        if requested_audio.path == current_audio_path:
            return AudioPreviewToggleResult(
                audio_id=None,
                audio_path=None,
                progress=0.0,
                is_playing=False,
                is_paused=False,
            )

        return AudioPreviewToggleResult(
            audio_id=requested_audio.wem_id,
            audio_path=requested_audio.path,
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
