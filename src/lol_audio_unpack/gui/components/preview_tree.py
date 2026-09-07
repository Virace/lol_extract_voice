"""基础试听树组件。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QTreeView
from qfluentwidgets import (
    CustomStyleSheet,
    isDarkTheme,
    setCustomStyleSheet,
    setStyleSheet,
)
from qfluentwidgets.components.widgets.scroll_bar import SmoothScrollDelegate

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.audio_scope import MappingNode
from lol_audio_unpack.app.audio_selection import AudioSelection
from lol_audio_unpack.gui.common.styles import (
    build_fluent_tree_shell_theme_pair,
    resolve_fluent_neutral_surface,
    resolve_fluent_text_primary_color,
)
from lol_audio_unpack.gui.components.audio_check import (
    CHECK_COLUMN_WIDTH,
    AudioCheckDelegate,
    audio_check_rect,
    draw_audio_check,
)
from lol_audio_unpack.gui.components.audio_row_style import (
    AUDIO_ROW_BUTTON_GAP,
    AUDIO_ROW_BUTTON_SIZE,
    AUDIO_ROW_HORIZONTAL_MARGIN,
    AUDIO_ROW_LEADING_SLOT_WIDTH,
    AUDIO_ROW_SELECTED_BAR_MARGIN,
    AUDIO_ROW_SELECTED_BAR_WIDTH,
    AUDIO_ROW_TEXT_GAP,
    active_audio_row_color,
    audio_control_colors,
    audio_progress_color,
    audio_selection_bar_color,
)

NODE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 1
AUDIO_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 2
AUDIO_AVAILABLE_ROLE = int(Qt.ItemDataRole.UserRole) + 3
NODE_PAYLOAD_ROLE = int(Qt.ItemDataRole.UserRole) + 4
NODE_LOADED_ROLE = int(Qt.ItemDataRole.UserRole) + 5
AUDIO_REF_ROLE = int(Qt.ItemDataRole.UserRole) + 6
AUDIO_AMBIGUOUS_ROLE = int(Qt.ItemDataRole.UserRole) + 7
EMPTY_MODEL_INDEX = QModelIndex()
PREVIEW_TREE_ITEM_MIN_HEIGHT = 20
PREVIEW_TREE_ROW_HORIZONTAL_MARGIN = AUDIO_ROW_HORIZONTAL_MARGIN
PREVIEW_TREE_BRANCH_SLOT_WIDTH = AUDIO_ROW_LEADING_SLOT_WIDTH
PREVIEW_TREE_BRANCH_ICON_SIZE = 12
PREVIEW_TREE_BRANCH_ICON_STROKE_WIDTH = 2
PREVIEW_TREE_TEXT_GAP = AUDIO_ROW_TEXT_GAP
PREVIEW_TREE_SELECTED_BAR_WIDTH = AUDIO_ROW_SELECTED_BAR_WIDTH
PREVIEW_TREE_SELECTED_BAR_MARGIN = AUDIO_ROW_SELECTED_BAR_MARGIN
PREVIEW_TREE_INDENTATION = 10
PREVIEW_TREE_AUDIO_BUTTON_SIZE = AUDIO_ROW_BUTTON_SIZE
PREVIEW_TREE_AUDIO_BUTTON_GAP = AUDIO_ROW_BUTTON_GAP
PREVIEW_MAPPING_ROOT_KEYS = ("skins", "map", "resourcePacks")


def _build_branch_styles() -> str:
    """构造 branch 区域样式。"""
    return """
    QTreeView::branch,
    QTreeView::branch:hover,
    QTreeView::branch:selected,
    QTreeView::branch:selected:hover,
    QTreeView::branch:has-siblings:!adjoins-item,
    QTreeView::branch:has-siblings:!adjoins-item:hover,
    QTreeView::branch:has-siblings:!adjoins-item:selected,
    QTreeView::branch:has-siblings:!adjoins-item:selected:hover,
    QTreeView::branch:adjoins-item,
    QTreeView::branch:adjoins-item:hover,
    QTreeView::branch:adjoins-item:selected,
    QTreeView::branch:adjoins-item:selected:hover,
    QTreeView::branch:has-siblings:adjoins-item,
    QTreeView::branch:!has-children:!has-siblings:adjoins-item,
    QTreeView::branch:closed:has-children:has-siblings,
    QTreeView::branch:closed:has-children:!has-siblings,
    QTreeView::branch:open:has-children:has-siblings,
    QTreeView::branch:open:has-children:!has-siblings {{
        background: transparent;
        border: none;
        margin: 0;
        padding: 0;
    }}
    """


def _build_styles() -> tuple[str, str]:
    """构造试听树的亮暗主题样式。"""
    branch_qss = _build_branch_styles()
    item_rules = """
        padding: 4px 8px 4px 0;
        margin: 2px 0;
        padding-left: 0;
    """
    # 顶部 2px 对齐英雄列表首项留白，水平内收统一由行绘制负责。
    return build_fluent_tree_shell_theme_pair(
        light_background="transparent",
        dark_background="transparent",
        is_border_visible=False,
        border_radius="10px",
        padding="2px 0 0 0",
        item_min_height=PREVIEW_TREE_ITEM_MIN_HEIGHT,
        item_border_radius=0,
        extra_item_rules=item_rules,
        extra_rules=branch_qss,
    )


def inject_preview_tree_style(tree_view: QTreeView) -> None:
    """为当前试听树注入局部 QSS。

    默认使用接近 Fluent 的自定义亮暗主题，并在其基础上提高树节点行高。
    若后续需要为试听树补充更多局部样式，继续只在这个函数内部追加，
    并仍然只挂载到当前 ``PreviewTreeView`` 实例。

    Args:
        tree_view: 当前要挂载局部样式的试听树实例。
    """
    light_qss, dark_qss = _build_styles()
    setCustomStyleSheet(tree_view, light_qss, dark_qss)
    setStyleSheet(tree_view, CustomStyleSheet(tree_view))


@dataclass(frozen=True, slots=True)
class TreeStats:
    """区分事件中的引用次数与映射范围内的实际文件数量。

    Attributes:
        audio_id_count: 事件中音频 ID 的出现次数，同 ID 跨事件重复计入。
        available_audio_id_count: 已解析到本地路径的引用次数，保留既有字段语义。
        unavailable_audio_count: 不可用映射项数量，不表示独立缺失文件数。
        available_file_count: 已解析引用按实际路径去重后的文件数量，不代表全目录总数。
    """

    skin_count: int = 0
    audio_type_count: int = 0
    event_count: int = 0
    audio_id_count: int = 0
    available_audio_id_count: int = 0
    unavailable_audio_count: int = 0
    available_file_count: int = 0


@dataclass(frozen=True, slots=True)
class PreviewFilterResult:
    """描述事件树过滤后的结构与命中统计。"""

    mapping_data: dict[str, Any] | None
    is_active: bool
    matched_event_count: int = 0
    matched_audio_id_count: int = 0


@dataclass(frozen=True, slots=True)
class PreviewModifierSummary:
    """描述预览树中可观察到的前缀/后缀修饰符集合。"""

    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()
    audio_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreviewSearchScope:
    """描述一次预览搜索的修饰符与关键字范围。"""

    modifier: str | None = None
    keyword: str = ""


@dataclass(frozen=True, slots=True)
class _EventAudioResolution:
    """描述一个事件音频 ID 的路径级可播放结果。"""

    audio_refs: tuple[AudioRef, ...] = ()
    is_ambiguous: bool = False
    missing_paths: tuple[str, ...] = ()

    @property
    def unavailable_count(self) -> int:
        """逐路径统计缺失；没有可靠路径的 ID 保留一个不可用叶子。"""
        return len(self.missing_paths) or int(not self.audio_refs)


@dataclass(slots=True)
class _PreviewTreeNode:
    """树形预览中的轻量节点。"""

    label: str
    kind: str
    payload: Any
    parent: _PreviewTreeNode | None = None
    audio_id: str | None = None
    audio_ref: AudioRef | None = None
    is_available: bool = False
    is_ambiguous: bool = False
    children: list[_PreviewTreeNode] | None = None
    children_loaded: bool = False
    key: tuple[str, ...] = ()
    members: frozenset[Path] | None = None
    missing_count: int = 0

    def row_in_parent(self) -> int:
        """返回当前节点在父节点中的行号。"""
        if self.parent is None or not self.parent.children:
            return 0
        return self.parent.children.index(self)


def extract_tree_groups(mapping_data: dict[str, Any] | None) -> dict[str, Any]:
    """从英雄、地图或资源包 mapping 中提取统一的首层分组。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。

    Returns:
        根分组字典；若数据缺失则返回空字典。
    """
    if not isinstance(mapping_data, dict):
        return {}

    for key in PREVIEW_MAPPING_ROOT_KEYS:
        payload = mapping_data.get(key)
        if key in mapping_data and isinstance(payload, dict):
            return payload
    return {}


def _build_audio_ref_indexes(
    audio_refs: tuple[AudioRef, ...],
) -> tuple[dict[str, tuple[AudioRef, ...]], dict[str, AudioRef]]:
    """按 WEM ID 与稳定相对路径建立音频引用索引。"""
    refs_by_id: dict[str, list[AudioRef]] = {}
    refs_by_path: dict[str, AudioRef] = {}
    for ref in audio_refs:
        refs_by_id.setdefault(ref.wem_id, []).append(ref)
        refs_by_path[ref.relative_path] = ref

    sorted_refs_by_id = {
        audio_id: tuple(sorted(refs, key=lambda item: item.relative_path)) for audio_id, refs in refs_by_id.items()
    }
    return sorted_refs_by_id, refs_by_path


def _event_audio_paths(
    paths_by_event: object,
    event_name: object,
) -> tuple[bool, tuple[str, ...]]:
    """读取事件的 mapping 路径，并区分缺失与显式空路径。"""
    if not isinstance(paths_by_event, dict) or event_name not in paths_by_event:
        return False, ()

    raw_paths = paths_by_event[event_name]
    if not isinstance(raw_paths, list | tuple):
        return True, ()
    return True, tuple(str(path).replace("\\", "/").strip("/") for path in raw_paths if str(path).strip())


def _index_event_refs(
    audio_paths: tuple[str, ...], refs_by_path: dict[str, AudioRef]
) -> dict[str, _EventAudioResolution]:
    """每个事件只扫描一次路径，避免万级叶子展开时逐 ID 重扫整个事件。"""
    refs: dict[str, dict[str, AudioRef]] = {}
    missing: dict[str, list[str]] = {}
    for path in dict.fromkeys(audio_paths):
        ref = refs_by_path.get(path)
        if ref is not None:
            refs.setdefault(ref.wem_id, {})[ref.key] = ref
        else:
            missing.setdefault(Path(path).stem, []).append(path)
    return {
        key: _EventAudioResolution(
            audio_refs=tuple(sorted(refs.get(key, {}).values(), key=lambda item: item.relative_path)),
            missing_paths=tuple(missing.get(key, ())),
        )
        for key in refs.keys() | missing.keys()
    }


def _resolve_event_audio_refs(
    audio_id: str,
    *,
    event_refs: dict[str, _EventAudioResolution],
    has_audio_paths: bool,
    refs_by_id: dict[str, tuple[AudioRef, ...]],
) -> _EventAudioResolution:
    """按事件 mapping 优先解析精确音频路径。"""
    if has_audio_paths:
        return event_refs.get(audio_id, _EventAudioResolution())

    fallback_refs = refs_by_id.get(audio_id, ())
    if len(fallback_refs) == 1:
        return _EventAudioResolution(audio_refs=fallback_refs)
    return _EventAudioResolution(is_ambiguous=len(fallback_refs) > 1)


def collect_tree_stats(
    mapping_data: dict[str, Any] | None,
    audio_refs: tuple[AudioRef, ...],
) -> TreeStats:
    """统计完整预览树中的层级与路径级可试听叶子数量。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。
        audio_refs: 当前实体本地已存在的路径级 WEM 引用。

    Returns:
        用于右侧摘要卡的统计数据。
    """
    groups = extract_tree_groups(mapping_data)
    if not isinstance(groups, dict):
        return TreeStats()

    group_count = 0
    audio_type_count = 0
    event_count = 0
    audio_id_count = 0
    available_audio_id_count = 0
    unavailable_audio_count = 0
    available_paths: set[Path] = set()
    refs_by_id, refs_by_path = _build_audio_ref_indexes(audio_refs)

    for group_payload in groups.values():
        if not isinstance(group_payload, dict):
            continue

        group_count += 1
        events_payload = group_payload.get("events", {})
        if not isinstance(events_payload, dict):
            continue
        audio_paths_payload = group_payload.get("audioPaths", {})

        for audio_type_name, event_group in events_payload.items():
            if not isinstance(event_group, dict):
                continue

            audio_type_count += 1
            paths_by_event = (
                audio_paths_payload.get(audio_type_name, {}) if isinstance(audio_paths_payload, dict) else {}
            )
            for event_name, audio_ids in event_group.items():
                if not isinstance(audio_ids, list | tuple):
                    continue

                event_count += 1
                has_audio_paths, audio_paths = _event_audio_paths(paths_by_event, event_name)
                event_refs = _index_event_refs(audio_paths, refs_by_path)
                for audio_id in audio_ids:
                    audio_id_text = str(audio_id).strip()
                    if not audio_id_text:
                        continue

                    audio_id_count += 1
                    resolution = _resolve_event_audio_refs(
                        audio_id_text,
                        event_refs=event_refs,
                        has_audio_paths=has_audio_paths,
                        refs_by_id=refs_by_id,
                    )
                    available_audio_id_count += len(resolution.audio_refs)
                    unavailable_audio_count += resolution.unavailable_count
                    # 多个事件可引用同一文件；文件数不能沿用事件叶子的累加值。
                    available_paths.update(ref.path for ref in resolution.audio_refs)

    return TreeStats(
        skin_count=group_count,
        audio_type_count=audio_type_count,
        event_count=event_count,
        audio_id_count=audio_id_count,
        available_audio_id_count=available_audio_id_count,
        unavailable_audio_count=unavailable_audio_count,
        available_file_count=len(available_paths),
    )


def build_tree_summary_text(stats: TreeStats) -> str:
    """构造预览树顶部摘要文案。

    Args:
        stats: 当前预览树的统计结果。

    Returns:
        供总览页恢复状态和展示详情的文本，首段为简短文件状态。
    """
    return (
        f"可用 {stats.available_file_count:,} 个文件 · 分组 {stats.skin_count} · "
        f"类型 {stats.audio_type_count} · 事件 {stats.event_count} · "
        f"可用引用 {stats.available_audio_id_count} 次 · 不可用映射 {stats.unavailable_audio_count} 项"
    )


def filter_preview_mapping_data(
    mapping_data: dict[str, Any] | None,
    keyword: str,
) -> PreviewFilterResult:
    """按关键字过滤事件树原始数据，同时保留必要祖先路径。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。
        keyword: 搜索关键字。

    Returns:
        过滤后的 mapping 数据与命中统计。
    """
    scope = parse_preview_search_scope(keyword)
    normalized = scope.keyword.casefold()
    modifier = scope.modifier.casefold() if scope.modifier else None
    if not modifier and not normalized:
        return PreviewFilterResult(mapping_data=mapping_data, is_active=False)

    groups = extract_tree_groups(mapping_data)
    if not groups:
        return PreviewFilterResult(mapping_data=mapping_data, is_active=True)

    filtered_groups: dict[str, dict[str, object]] = {}
    matched_event_count = 0
    matched_audio_id_count = 0

    for group_id, group_payload in groups.items():
        if not isinstance(group_payload, dict):
            continue

        events_payload = group_payload.get("events", {})
        if not isinstance(events_payload, dict):
            continue

        audio_paths_payload = group_payload.get("audioPaths", {})
        filtered_audio_types: dict[str, dict[str, list[str]]] = {}
        filtered_audio_paths: dict[str, dict[str, list[str]]] = {}
        for audio_type_name, event_payload in events_payload.items():
            if not isinstance(event_payload, dict):
                continue

            audio_type = str(audio_type_name).strip()
            if modifier and not _audio_type_matches_modifier(audio_type, modifier):
                continue

            paths_by_event = (
                audio_paths_payload.get(audio_type_name, {}) if isinstance(audio_paths_payload, dict) else {}
            )
            filtered_events: dict[str, list[str]] = {}
            filtered_paths: dict[str, list[str]] = {}
            for event_name, audio_ids in event_payload.items():
                if not isinstance(audio_ids, list | tuple):
                    continue

                event_label = str(event_name)
                clean_audio_ids = [str(audio_id).strip() for audio_id in audio_ids if str(audio_id).strip()]
                event_match = not normalized or normalized in event_label.casefold()
                matched_audio_ids = [audio_id for audio_id in clean_audio_ids if normalized in audio_id.casefold()]

                if event_match:
                    filtered_events[event_label] = clean_audio_ids
                    event_paths = paths_by_event.get(event_name, ()) if isinstance(paths_by_event, dict) else ()
                    if isinstance(event_paths, list | tuple):
                        filtered_paths[event_label] = [str(path).strip() for path in event_paths if str(path).strip()]
                    matched_event_count += 1
                    matched_audio_id_count += len(clean_audio_ids)
                    continue

                if not matched_audio_ids:
                    continue

                filtered_events[event_label] = matched_audio_ids
                event_paths = paths_by_event.get(event_name, ()) if isinstance(paths_by_event, dict) else ()
                if isinstance(event_paths, list | tuple):
                    matched_ids = set(matched_audio_ids)
                    filtered_paths[event_label] = [
                        str(path).strip()
                        for path in event_paths
                        if str(path).strip() and Path(str(path)).stem in matched_ids
                    ]
                matched_event_count += 1
                matched_audio_id_count += len(matched_audio_ids)

            if filtered_events:
                filtered_audio_types[str(audio_type_name)] = filtered_events
                if filtered_paths:
                    filtered_audio_paths[str(audio_type_name)] = filtered_paths

        if filtered_audio_types:
            group_result: dict[str, object] = {"events": filtered_audio_types}
            if filtered_audio_paths:
                group_result["audioPaths"] = filtered_audio_paths
            filtered_groups[str(group_id)] = group_result

    root_key = next(
        (key for key in PREVIEW_MAPPING_ROOT_KEYS if isinstance(mapping_data, dict) and key in mapping_data),
        "skins",
    )
    return PreviewFilterResult(
        mapping_data={root_key: filtered_groups},
        is_active=True,
        matched_event_count=matched_event_count,
        matched_audio_id_count=matched_audio_id_count,
    )


def parse_preview_search_scope(keyword: str) -> PreviewSearchScope:
    """解析搜索串中的动态修饰符范围。

    Args:
        keyword: 原始搜索字符串。

    Returns:
        解析后的修饰符与实际关键字。
    """
    raw = keyword.strip()
    if ":" not in raw:
        return PreviewSearchScope(keyword=raw)

    modifier_text, content = raw.split(":", 1)
    modifier = modifier_text.strip()
    if not modifier:
        return PreviewSearchScope(keyword=raw)

    return PreviewSearchScope(modifier=modifier, keyword=content.strip())


def _audio_type_matches_modifier(audio_type: str, modifier: str) -> bool:
    """判断音频类型是否匹配给定的动态修饰符。"""
    audio_type_text = audio_type.strip()
    if not audio_type_text:
        return False

    normalized_audio_type = audio_type_text.casefold()
    if normalized_audio_type == modifier:
        return True

    parts = tuple(part.casefold() for part in audio_type_text.split("_") if part.strip())
    if not parts:
        return False
    return parts[0] == modifier or parts[-1] == modifier


def extract_preview_modifiers(mapping_data: dict[str, Any] | None) -> PreviewModifierSummary:
    """从当前预览树数据中提取音频类型前缀/后缀修饰符。

    Args:
        mapping_data: 当前实体的原始 mapping 数据。

    Returns:
        去重后的前缀、后缀与完整音频类型名集合。
    """
    groups = extract_tree_groups(mapping_data)
    if not groups:
        return PreviewModifierSummary()

    prefixes: set[str] = set()
    suffixes: set[str] = set()
    audio_types: set[str] = set()

    for group_payload in groups.values():
        if not isinstance(group_payload, dict):
            continue

        events_payload = group_payload.get("events", {})
        if not isinstance(events_payload, dict):
            continue

        for audio_type_name in events_payload.keys():
            audio_type = str(audio_type_name).strip()
            if not audio_type:
                continue

            audio_types.add(audio_type)
            parts = tuple(part.strip() for part in audio_type.split("_") if part.strip())
            if not parts:
                continue

            prefixes.add(parts[0])
            suffixes.add(parts[-1])

    def sort_key(value: str) -> str:
        return value.casefold()

    return PreviewModifierSummary(
        prefixes=tuple(sorted(prefixes, key=sort_key)),
        suffixes=tuple(sorted(suffixes, key=sort_key)),
        audio_types=tuple(sorted(audio_types, key=sort_key)),
    )


class PreviewTreeModel(QAbstractItemModel):
    """基础试听树数据模型。"""

    selection_changed = Signal()

    def __init__(self, parent=None) -> None:
        """初始化树模型。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._audio_refs_by_id: dict[str, tuple[AudioRef, ...]] = {}
        self._audio_refs_by_path: dict[str, AudioRef] = {}
        self._root_nodes: list[_PreviewTreeNode] = []
        self.audio_selection: AudioSelection | None = None
        self.mapping_source: MappingNode | None = None
        self.selection_mode = False
        self._scope_groups: dict[str, Any] = {}

    def clear_preview(self) -> None:
        """清空当前预览树内容。"""
        self.beginResetModel()
        self._audio_refs_by_id = {}
        self._audio_refs_by_path = {}
        self._root_nodes = []
        self.endResetModel()

    def set_preview_data(
        self,
        mapping_data: dict[str, Any] | None,
        audio_refs: tuple[AudioRef, ...],
        group_label_map: dict[str, str] | None = None,
        selection_mapping: dict[str, Any] | None = None,
    ) -> None:
        """替换当前预览树数据。

        Args:
            mapping_data: 当前实体的原始 mapping 数据。
            audio_refs: 当前实体全部已解包 WEM 的路径级稳定引用。
            group_label_map: 可选的首层分组文案映射，仅影响展示标签。
        """
        groups = extract_tree_groups(mapping_data)
        root_nodes: list[_PreviewTreeNode] = []
        display_label_map = group_label_map or {}

        for group_id, group_payload in groups.items():
            if not isinstance(group_payload, dict):
                continue
            root_nodes.append(
                _PreviewTreeNode(
                    label=display_label_map.get(str(group_id), str(group_id)),
                    kind="group",
                    payload=group_payload,
                    key=(str(group_id),),
                )
            )

        self.beginResetModel()
        self._audio_refs_by_id, self._audio_refs_by_path = _build_audio_ref_indexes(audio_refs)
        self._root_nodes = root_nodes
        self._scope_groups = {
            str(key): value
            for key, value in extract_tree_groups(
                selection_mapping if selection_mapping is not None else mapping_data
            ).items()
        }
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回指定父节点下的子节点数量。

        Args:
            parent: 父节点索引。

        Returns:
            当前父节点下已加载的子节点数量。
        """
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            return len(self._root_nodes)

        node = self._node_from_index(parent)
        if node is None or not node.children_loaded or node.children is None:
            return 0
        return len(node.children)

    def columnCount(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> int:
        """返回模型列数。

        Args:
            parent: 父节点索引。

        Returns:
            固定为单列。
        """
        return 1

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex = EMPTY_MODEL_INDEX,
    ) -> QModelIndex:
        """根据父节点和行号创建子节点索引。

        Args:
            row: 目标行号。
            column: 目标列号。
            parent: 父节点索引。

        Returns:
            对应的模型索引；若越界则返回空索引。
        """
        if column != 0 or row < 0:
            return QModelIndex()

        children = self._root_nodes if not parent.isValid() else self._children_for_parent(parent)
        if children is None or row >= len(children):
            return QModelIndex()

        return self.createIndex(row, column, children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        """返回当前索引的父节点索引。

        Args:
            index: 当前节点索引。

        Returns:
            父节点索引；若当前为根节点则返回空索引。
        """
        if not index.isValid():
            return QModelIndex()

        node = self._node_from_index(index)
        if node is None or node.parent is None:
            return QModelIndex()

        parent_node = node.parent
        if parent_node.parent is None:
            row = self._root_nodes.index(parent_node)
        else:
            row = parent_node.row_in_parent()
        return self.createIndex(row, 0, parent_node)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        """按角色返回预览树节点信息。

        Args:
            index: 当前节点索引。
            role: 目标数据角色。

        Returns:
            对应角色的数据；若索引无效则返回 ``None``。
        """
        node = self._node_from_index(index)
        if node is None:
            return None

        value: Any = None
        if role == Qt.ItemDataRole.DisplayRole:
            value = node.label
        elif role == NODE_KIND_ROLE:
            value = node.kind
        elif role == AUDIO_ID_ROLE:
            value = node.audio_id
        elif role == AUDIO_AVAILABLE_ROLE:
            value = node.is_available
        elif role == AUDIO_REF_ROLE:
            value = node.audio_ref
        elif role == AUDIO_AMBIGUOUS_ROLE:
            value = node.is_ambiguous
        elif role == NODE_PAYLOAD_ROLE:
            value = node.payload
        elif role == NODE_LOADED_ROLE:
            value = node.children_loaded
        elif role == Qt.ItemDataRole.CheckStateRole and self.selection_mode:
            members = self.selection_paths(index)
            count = self.audio_selection.count_paths(members) if self.audio_selection is not None else 0
            value = (
                Qt.CheckState.Checked
                if members and count == len(members)
                else (Qt.CheckState.PartiallyChecked if count else Qt.CheckState.Unchecked)
            )
        elif role == Qt.ItemDataRole.ToolTipRole and self.selection_mode:
            members = self.selection_paths(index)
            count = self.audio_selection.count_paths(members) if self.audio_selection is not None else 0
            value = f"已选 {count}/{len(members)} 个可用音频；另有 {node.missing_count} 个对应文件不可用"
        return value

    def selection_paths(self, index: QModelIndex) -> frozenset[Path]:
        """读取节点完整范围中的可用路径，不要求展开，也不按搜索结果缩小父节点。"""
        node = self._node_from_index(index)
        if node is None:
            return frozenset()
        if node.members is not None:
            return node.members
        if node.kind == "audio_id":
            node.members = frozenset((node.audio_ref.path,)) if node.audio_ref is not None else frozenset()
            node.missing_count = int(node.audio_ref is None)
            return node.members
        group = self._scope_groups.get(node.key[0], {})
        events = group.get("events", {})
        paths = group.get("audioPaths", {})
        members: set[Path] = set()
        missing = 0
        for audio_type, event_group in events.items():
            if len(node.key) > 1 and str(audio_type) != node.key[1]:
                continue
            if not isinstance(event_group, dict):
                continue
            for event_name, audio_ids in event_group.items():
                if node.kind == "event" and str(event_name) != node.key[2]:
                    continue
                if not isinstance(audio_ids, list | tuple):
                    continue
                has_paths, event_paths = _event_audio_paths(paths.get(audio_type, {}), event_name)
                ids = {str(value) for value in audio_ids}
                event_refs = _index_event_refs(event_paths, self._audio_refs_by_path)
                for audio_id in ids:
                    resolution = _resolve_event_audio_refs(
                        audio_id,
                        event_refs=event_refs,
                        has_audio_paths=has_paths,
                        refs_by_id=self._audio_refs_by_id,
                    )
                    members.update(ref.path for ref in resolution.audio_refs)
                    missing += resolution.unavailable_count
        node.members = frozenset(members)
        node.missing_count = missing
        return node.members

    def setData(self, index: QModelIndex, value: Any, role: int = int(Qt.ItemDataRole.EditRole)) -> bool:
        """把复选框动作交给共享选择，保留浏览焦点和懒加载树。"""
        if role != Qt.ItemDataRole.CheckStateRole or not self.selection_mode or self.audio_selection is None:
            return False
        members = self.selection_paths(index)
        if not members:
            return False
        checked = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
        node = self.scope_node(index)
        if node is not None:
            self.audio_selection.set_node(node, members, checked)
        else:
            self.audio_selection.set_paths(members, checked)
        self.selection_changed.emit()
        return True

    def scope_node(self, index: QModelIndex) -> MappingNode | None:
        """为有精确路径的父节点提供稳定引用，旧映射继续使用已解析文件。"""
        node = self._node_from_index(index)
        if node is None or node.kind == "audio_id" or self.mapping_source is None:
            return None
        group = self._scope_groups.get(node.key[0], {})
        paths = group.get("audioPaths", {})
        for kind, events in group.get("events", {}).items():
            if len(node.key) > 1 and str(kind) != node.key[1]:
                continue
            for event in events:
                if node.kind == "event" and str(event) != node.key[2]:
                    continue
                if event not in paths.get(kind, {}):
                    return None
        return replace(self.mapping_source, key=node.key)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """返回当前节点的基础交互标记。

        Args:
            index: 当前节点索引。

        Returns:
            有效节点统一允许启用与选择。
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self.selection_mode and self.selection_paths(index):
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def hasChildren(self, parent: QModelIndex = EMPTY_MODEL_INDEX) -> bool:
        """判断某个节点是否还拥有下一层子节点。

        Args:
            parent: 父节点索引。

        Returns:
            是否还有下一层可展开内容。
        """
        if not parent.isValid():
            return bool(self._root_nodes)

        node = self._node_from_index(parent)
        if node is None:
            return False
        return self._node_has_children(node.kind, node.payload)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        """提供树视图列标题。

        Args:
            section: 列号。
            orientation: 表头方向。
            role: 目标数据角色。

        Returns:
            首列标题文本；其余场景返回 ``None``。
        """
        if orientation == Qt.Orientation.Horizontal and section == 0 and role == Qt.ItemDataRole.DisplayRole:
            return "试听视图"
        return None

    def ensure_children_loaded(self, index: QModelIndex) -> None:
        """在节点首次展开时填充下一层子节点。

        Args:
            index: 需要加载子节点的父索引。
        """
        node = self._node_from_index(index)
        if node is None or node.kind == "audio_id" or node.children_loaded:
            return

        children = self._build_children(node)
        if children:
            self.beginInsertRows(index, 0, len(children) - 1)
            node.children = children
            node.children_loaded = True
            self.endInsertRows()
            return

        node.children = []
        node.children_loaded = True

    def _children_for_parent(self, parent: QModelIndex) -> list[_PreviewTreeNode] | None:
        """返回父节点当前已加载的子节点列表。"""
        node = self._node_from_index(parent)
        if node is None or not node.children_loaded:
            return None
        return node.children or []

    def _node_from_index(self, index: QModelIndex) -> _PreviewTreeNode | None:
        """从模型索引中取回内部节点。"""
        if not index.isValid():
            return None
        node = index.internalPointer()
        return node if isinstance(node, _PreviewTreeNode) else None

    def _build_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """根据当前节点类别构造下一层子节点。"""
        if node.kind == "group":
            return self._build_audio_type_children(node)
        if node.kind == "audio_type":
            return self._build_event_children(node)
        if node.kind == "event":
            return self._build_audio_id_children(node)
        return []

    def _build_audio_type_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造分组节点下的音频类别子节点。"""
        payload = node.payload
        if not isinstance(payload, dict):
            return []

        events_payload = payload.get("events", {})
        audio_paths_payload = payload.get("audioPaths", {})
        if not isinstance(events_payload, dict):
            return []

        children: list[_PreviewTreeNode] = []
        for audio_type_name, event_payload in events_payload.items():
            if not isinstance(event_payload, dict):
                continue
            paths_by_event = (
                audio_paths_payload.get(audio_type_name, {}) if isinstance(audio_paths_payload, dict) else {}
            )
            children.append(
                _PreviewTreeNode(
                    label=str(audio_type_name),
                    kind="audio_type",
                    payload={"events": event_payload, "audio_paths": paths_by_event},
                    parent=node,
                    key=(*node.key, str(audio_type_name)),
                )
            )
        return children

    def _build_event_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造音频类别节点下的事件子节点。"""
        payload = node.payload
        if not isinstance(payload, dict):
            return []

        events_payload = payload.get("events", {})
        audio_paths_payload = payload.get("audio_paths", {})
        if not isinstance(events_payload, dict):
            return []

        children: list[_PreviewTreeNode] = []
        for event_name, audio_ids in events_payload.items():
            if not isinstance(audio_ids, list | tuple):
                continue
            has_audio_paths, audio_paths = _event_audio_paths(audio_paths_payload, event_name)
            children.append(
                _PreviewTreeNode(
                    label=str(event_name),
                    kind="event",
                    payload={
                        "audio_ids": [str(audio_id).strip() for audio_id in audio_ids if str(audio_id).strip()],
                        "audio_paths": list(audio_paths),
                        "has_audio_paths": has_audio_paths,
                    },
                    parent=node,
                    key=(*node.key, str(event_name)),
                )
            )
        return children

    def _build_audio_id_children(self, node: _PreviewTreeNode) -> list[_PreviewTreeNode]:
        """构造事件节点下的精确音频叶子节点。

        新 mapping 的 ``audioPaths`` 能把同 ID 的多条物理 WEM 精确展开；
        旧 mapping 仅在 ID 唯一时回退，避免字典序路径造成误播。
        """
        payload = node.payload
        if not isinstance(payload, dict):
            return []

        audio_ids = payload.get("audio_ids", ())
        audio_paths = payload.get("audio_paths", ())
        if not isinstance(audio_ids, list | tuple):
            return []

        event_refs = _index_event_refs(tuple(audio_paths), self._audio_refs_by_path)
        children: list[_PreviewTreeNode] = []
        for audio_id in audio_ids:
            audio_id_text = str(audio_id).strip()
            if not audio_id_text:
                continue
            resolution = _resolve_event_audio_refs(
                audio_id_text,
                event_refs=event_refs,
                has_audio_paths=bool(payload.get("has_audio_paths")),
                refs_by_id=self._audio_refs_by_id,
            )
            if resolution.audio_refs:
                children.extend(self._build_audio_ref_nodes(node, audio_id_text, resolution.audio_refs))
            if resolution.missing_paths:
                children.extend(
                    _PreviewTreeNode(
                        label=f"{audio_id_text}（映射路径当前不可用：{path}）",
                        kind="audio_id",
                        payload=None,
                        parent=node,
                        audio_id=audio_id_text,
                        children=[],
                        children_loaded=True,
                    )
                    for path in resolution.missing_paths
                )
            if resolution.audio_refs or resolution.missing_paths:
                continue

            has_audio_paths = bool(payload.get("has_audio_paths"))
            if resolution.is_ambiguous:
                label = f"{audio_id_text}（多个路径，请到全部音频选择）"
            elif has_audio_paths:
                label = f"{audio_id_text}（映射路径当前不可用）"
            else:
                label = audio_id_text
            children.append(
                _PreviewTreeNode(
                    label=label,
                    kind="audio_id",
                    payload=None,
                    parent=node,
                    audio_id=audio_id_text,
                    is_ambiguous=resolution.is_ambiguous,
                    children=[],
                    children_loaded=True,
                )
            )
        return children

    @staticmethod
    def _build_audio_ref_nodes(
        parent: _PreviewTreeNode,
        audio_id: str,
        refs: tuple[AudioRef, ...],
    ) -> list[_PreviewTreeNode]:
        """为每条已验证路径创建可播放的事件树叶子。"""
        return [
            _PreviewTreeNode(
                label=audio_id,
                kind="audio_id",
                payload=ref,
                parent=parent,
                audio_id=audio_id,
                audio_ref=ref,
                is_available=True,
                children=[],
                children_loaded=True,
            )
            for ref in refs
        ]

    def _node_has_children(self, kind: str, payload: Any) -> bool:
        """判断一个节点是否还有下一层可展开内容。"""
        if kind == "group":
            return isinstance(payload, dict) and isinstance(payload.get("events"), dict) and bool(payload["events"])
        if kind == "audio_type":
            return isinstance(payload, dict) and isinstance(payload.get("events"), dict) and bool(payload["events"])
        if kind == "event":
            audio_ids = payload.get("audio_ids", ()) if isinstance(payload, dict) else ()
            return isinstance(audio_ids, list | tuple) and any(str(item).strip() for item in audio_ids)
        return False


class PreviewTreeView(QTreeView):
    """最基础的试听树视图。"""

    audio_ref_toggle_requested = Signal(object)
    audio_context_menu_requested = Signal(object, QPoint)
    audio_ref_selected = Signal(object)
    node_export_requested = Signal(object, QPoint)

    def _index_depth(self, index: QModelIndex) -> int:
        """返回当前节点深度。"""
        depth = 0
        current = index.parent()
        while current.isValid():
            depth += 1
            current = current.parent()
        return depth

    def _row_rect(self, option) -> QRect:
        """返回整行背景矩形。"""
        return QRect(
            PREVIEW_TREE_ROW_HORIZONTAL_MARGIN,
            option.rect.top() + 2,
            max(0, self.viewport().width() - PREVIEW_TREE_ROW_HORIZONTAL_MARGIN * 2),
            max(0, option.rect.height() - 4),
        )

    def _content_rect(self, option, index: QModelIndex) -> QRect:
        """返回文本内容绘制区域。"""
        row_rect = self._row_rect(option)
        depth = self._index_depth(index)
        icon_span = max(PREVIEW_TREE_BRANCH_SLOT_WIDTH, PREVIEW_TREE_BRANCH_ICON_SIZE)
        content_left = row_rect.left() + depth * self.indentation() + icon_span + PREVIEW_TREE_TEXT_GAP
        audio_control_rect = self._audio_control_rect(row_rect, index)
        if not audio_control_rect.isNull():
            content_left = audio_control_rect.left() + audio_control_rect.width() + PREVIEW_TREE_AUDIO_BUTTON_GAP
        return QRect(
            content_left,
            option.rect.top(),
            max(0, row_rect.right() - content_left - 8 - (CHECK_COLUMN_WIDTH if self.model().selection_mode else 0)),
            option.rect.height(),
        )

    def _audio_control_rect(self, row_rect: QRect, index: QModelIndex) -> QRect:
        """返回音频叶子行左侧播放按钮区域。"""
        if not self._is_audio_leaf(index) or not self._is_audio_available(index):
            return QRect()

        depth = self._index_depth(index)
        icon_span = max(PREVIEW_TREE_BRANCH_SLOT_WIDTH, PREVIEW_TREE_BRANCH_ICON_SIZE)
        button_left = row_rect.left() + depth * self.indentation() + icon_span + PREVIEW_TREE_TEXT_GAP
        button_size = max(12, min(PREVIEW_TREE_AUDIO_BUTTON_SIZE, row_rect.height() - 8))
        return QRect(
            button_left,
            row_rect.center().y() - button_size // 2,
            button_size,
            button_size,
        )

    def _audio_control_rect_for_index(self, index: QModelIndex) -> QRect:
        """按当前可视区域计算音频叶子行的播放按钮矩形。"""
        visual_rect = self.visualRect(index)
        if not index.isValid() or not visual_rect.isValid() or visual_rect.isEmpty():
            return QRect()
        row_rect = QRect(
            PREVIEW_TREE_ROW_HORIZONTAL_MARGIN,
            visual_rect.top() + 2,
            max(0, self.viewport().width() - PREVIEW_TREE_ROW_HORIZONTAL_MARGIN * 2),
            max(0, visual_rect.height() - 4),
        )
        return self._audio_control_rect(row_rect, index)

    def _draw_selected_bar(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """绘制选中竖条。"""
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        if not is_selected:
            return

        bar_rect = QRect(
            row_rect.left() + PREVIEW_TREE_SELECTED_BAR_MARGIN,
            row_rect.top() + 7,
            PREVIEW_TREE_SELECTED_BAR_WIDTH,
            max(0, row_rect.height() - 14),
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(audio_selection_bar_color(is_dark=isDarkTheme()))
        painter.drawRoundedRect(bar_rect, 2, 2)
        painter.restore()

    def _draw_branch_icon(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """按当前层级绘制展开/收缩图标。"""
        if not self._has_expand_icon(index):
            return

        depth = self._index_depth(index)
        slot_left = row_rect.left() + depth * self.indentation()
        icon_size = PREVIEW_TREE_BRANCH_ICON_SIZE
        icon_rect = QRect(
            slot_left + (PREVIEW_TREE_BRANCH_SLOT_WIDTH - icon_size) // 2,
            row_rect.center().y() - icon_size // 2 + 1,
            icon_size,
            icon_size,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(resolve_fluent_text_primary_color(), PREVIEW_TREE_BRANCH_ICON_STROKE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        center = icon_rect.center()
        half_w = icon_rect.width() / 2
        half_h = icon_rect.height() / 2
        if self.isExpanded(index):
            points = (
                QPointF(center.x() - half_w * 0.55, center.y() - half_h * 0.2),
                QPointF(center.x(), center.y() + half_h * 0.35),
                QPointF(center.x() + half_w * 0.55, center.y() - half_h * 0.2),
            )
        else:
            points = (
                QPointF(center.x() - half_w * 0.2, center.y() - half_h * 0.55),
                QPointF(center.x() + half_w * 0.35, center.y()),
                QPointF(center.x() - half_w * 0.2, center.y() + half_h * 0.55),
            )
        painter.drawLine(points[0], points[1])
        painter.drawLine(points[1], points[2])
        painter.restore()

    def _hovered_index_at_y(self, pos_y: int) -> QModelIndex:
        """按行命中 hover 索引，避免受 branch 子控件分块影响。"""
        probe_xs = (
            max(1, self.viewport().width() - 8),
            max(1, self.viewport().width() // 2),
            min(max(1, self.indentation() + 24), max(1, self.viewport().width() - 1)),
        )
        for probe_x in probe_xs:
            index = self.indexAt(QPoint(probe_x, pos_y))
            if index.isValid():
                return index
        return QModelIndex()

    def _has_expand_icon(self, index: QModelIndex) -> bool:
        """返回当前节点是否应显示展开/收缩尖号。"""
        model = self.model()
        return model is not None and model.hasChildren(index)

    def _current_row_color(self, index: QModelIndex) -> QColor | None:
        """返回当前行的自定义背景色。"""
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        is_hovered = index == self._hovered_index
        audio_ref = self._audio_ref_for_index(index)
        is_active_audio = audio_ref is not None and audio_ref.path == self._active_audio_path
        if not is_selected and not is_hovered and not is_active_audio:
            return None

        if is_active_audio and not is_selected and not is_hovered:
            return active_audio_row_color(is_dark=isDarkTheme())
        return resolve_fluent_neutral_surface("emphasis_selected" if is_selected else "emphasis_hover")

    def _audio_id_for_index(self, index: QModelIndex) -> str | None:
        """返回指定索引对应的音频 ID。"""
        model = self.model()
        if model is None:
            return None
        audio_id = model.data(index, AUDIO_ID_ROLE)
        if audio_id is None:
            return None
        text = str(audio_id).strip()
        return text or None

    def _audio_ref_for_index(self, index: QModelIndex) -> AudioRef | None:
        """返回指定索引对应的精确 WEM 引用。"""
        model = self.model()
        if model is None:
            return None
        ref = model.data(index, AUDIO_REF_ROLE)
        return ref if isinstance(ref, AudioRef) else None

    def _is_audio_leaf(self, index: QModelIndex) -> bool:
        """判断索引是否为音频 ID 叶子节点。"""
        model = self.model()
        return bool(index.isValid() and model is not None and model.data(index, NODE_KIND_ROLE) == "audio_id")

    def _is_audio_available(self, index: QModelIndex) -> bool:
        """判断索引是否为本地可试听的音频叶子节点。"""
        return self._audio_ref_for_index(index) is not None

    def _context_audio_ref_at(self, pos: QPoint) -> AudioRef | None:
        """解析右键位置命中的精确可用音频引用。"""
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        if not self._is_audio_leaf(index) or not self._is_audio_available(index):
            return None
        return self._audio_ref_for_index(index)

    def _playback_progress_for_index(self, index: QModelIndex) -> float:
        """返回当前行的试听进度。"""
        audio_ref = self._audio_ref_for_index(index)
        if audio_ref is None or audio_ref.path != self._active_audio_path:
            return 0.0
        return max(0.0, min(1.0, self._active_audio_progress))

    def _draw_playback_progress(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """为当前正在试听的叶子行绘制整行进度背景。"""
        progress = self._playback_progress_for_index(index)
        if progress <= 0:
            return

        progress_color = audio_progress_color(
            is_dark=isDarkTheme(),
            is_playing=self._active_audio_is_playing,
        )
        progress_width = max(0, min(row_rect.width(), int(round(row_rect.width() * progress))))
        if progress_width <= 0:
            return

        clip_rect = QRect(row_rect.left(), row_rect.top(), progress_width, row_rect.height())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setClipRect(clip_rect)
        painter.setBrush(progress_color)
        painter.drawRoundedRect(row_rect, 6, 6)
        painter.restore()

    def _stop_icon_rect(self, button_rect: QRect) -> QRect:
        """返回播放中停止方块的居中矩形。"""
        side = max(6, min(button_rect.width(), button_rect.height()) - 10)
        rect = QRect(0, 0, side, side)
        rect.moveCenter(button_rect.center())
        return rect

    def _draw_audio_control(self, painter: QPainter, row_rect: QRect, index: QModelIndex) -> None:
        """为可试听叶子行绘制播放/停止按钮。"""
        button_rect = self._audio_control_rect(row_rect, index)
        if button_rect.isNull():
            return

        audio_ref = self._audio_ref_for_index(index)
        is_active_audio = audio_ref is not None and audio_ref.path == self._active_audio_path
        if is_active_audio:
            button_background, icon_color = audio_control_colors(is_dark=isDarkTheme())
        else:
            button_background = resolve_fluent_neutral_surface("emphasis_hover")
            button_background.setAlpha(20)
            icon_color = resolve_fluent_text_primary_color()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(button_background)
        painter.drawRoundedRect(button_rect, 5, 5)
        painter.setBrush(icon_color)
        if is_active_audio and self._active_audio_is_playing:
            painter.drawRoundedRect(self._stop_icon_rect(button_rect), 1, 1)
        else:
            points = QPolygonF(
                (
                    QPointF(
                        button_rect.left() + button_rect.width() * 0.36, button_rect.top() + button_rect.height() * 0.26
                    ),
                    QPointF(
                        button_rect.left() + button_rect.width() * 0.36,
                        button_rect.bottom() - button_rect.height() * 0.26,
                    ),
                    QPointF(button_rect.right() - button_rect.width() * 0.24, button_rect.center().y()),
                )
            )
            painter.drawPolygon(points)
        painter.restore()

    def __init__(self, parent=None) -> None:
        """初始化树视图。

        Args:
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._hovered_index = QModelIndex()
        self._active_audio_path: Path | None = None
        self._active_audio_progress = 0.0
        self._active_audio_is_playing = False
        self._active_audio_is_paused = False
        model = PreviewTreeModel(self)
        self.setModel(model)
        self.setItemDelegate(AudioCheckDelegate(self))
        self.setUniformRowHeights(True)
        self.setHeaderHidden(True)
        self.setIndentation(PREVIEW_TREE_INDENTATION)
        self.setAnimated(True)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setVerticalScrollMode(QTreeView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QTreeView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(18)
        self.scrollDelegate = SmoothScrollDelegate(self, True)
        inject_preview_tree_style(self)
        self.expanded.connect(model.ensure_children_loaded)
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """在用户选择精确事件叶子时上报其稳定音频引用。"""
        audio_ref = self._audio_ref_for_index(current)
        if audio_ref is not None:
            self.audio_ref_selected.emit(audio_ref)

    def viewportEvent(self, event) -> bool:
        """跟踪 hover 行并触发重绘。"""
        if event.type() == QEvent.Type.HoverMove:
            hovered_index = self._hovered_index_at_y(event.position().toPoint().y())
            if hovered_index != self._hovered_index:
                self._hovered_index = hovered_index
                self.viewport().update()
        elif event.type() in {QEvent.Type.HoverLeave, QEvent.Type.Leave}:
            if self._hovered_index.isValid():
                self._hovered_index = QModelIndex()
                self.viewport().update()
        return super().viewportEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """拦截叶子行播放按钮点击，避免落入默认选择逻辑。"""
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position().toPoint()
            index = self._hovered_index_at_y(click_pos.y())
            if self.model().selection_mode and audio_check_rect(
                self.visualRect(index), self.viewport().width()
            ).contains(click_pos):
                self._toggle_export_check(index)
                event.accept()
                return
            button_rect = self._audio_control_rect_for_index(index)
            audio_ref = self._audio_ref_for_index(index)
            if audio_ref is not None and button_rect.contains(click_pos):
                self.audio_ref_toggle_requested.emit(audio_ref)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        """只在右键命中可试听音频叶子项时请求页面展示菜单。"""
        audio_ref = self._context_audio_ref_at(event.pos())
        if audio_ref is None:
            index = self.indexAt(event.pos())
            if index.isValid() and self.model().selection_paths(index):
                self.node_export_requested.emit(index, event.globalPos())
                event.accept()
                return
            event.ignore()
            return
        self.audio_context_menu_requested.emit(audio_ref, event.globalPos())
        event.accept()

    def _toggle_export_check(self, index: QModelIndex) -> None:
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        self.model().setData(
            index,
            Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )

    def keyPressEvent(self, event) -> None:
        """选择模式下用空格切换复选框，其他键保留树导航语义。"""
        if event.key() == Qt.Key.Key_Space and self.model().selection_mode:
            self._toggle_export_check(self.currentIndex())
            event.accept()
            return
        super().keyPressEvent(event)

    def refresh_export_selection(self, *, only_selected: bool = False) -> None:
        """只过滤已加载行；父节点成员来自原始数据，不为了筛选展开全树。"""
        was_filtered = getattr(self, "_only_selected", False)
        self._only_selected = only_selected
        if not was_filtered and not only_selected:
            self.viewport().update()
            return
        model = self.model()

        def visit(parent: QModelIndex) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                members = model.selection_paths(index) if only_selected else frozenset()
                selected = model.audio_selection.count_paths(members) if model.audio_selection is not None else 0
                self.setRowHidden(row, parent, only_selected and not selected)
                if model.rowCount(index):
                    visit(index)

        visit(QModelIndex())
        self.viewport().update()

    def drawBranches(self, painter: QPainter, rect: QRect, index: QModelIndex) -> None:
        """只绘制展开/收缩图标，避免默认 branch 连接线与背景叠加。"""
        return

    def drawRow(self, painter: QPainter, option, index: QModelIndex) -> None:
        """绘制统一的整行 hover/selected 背景。"""
        row_color = self._current_row_color(index)
        row_rect = self._row_rect(option)
        if row_color is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setClipping(False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(row_color)
            painter.drawRoundedRect(row_rect, 6, 6)
            painter.restore()

        self._draw_playback_progress(painter, row_rect, index)
        self._draw_selected_bar(painter, row_rect, index)
        self._draw_branch_icon(painter, row_rect, index)
        self._draw_audio_control(painter, row_rect, index)
        if self.model().selection_mode:
            draw_audio_check(
                self,
                painter,
                audio_check_rect(row_rect, self.viewport().width()),
                index.data(Qt.ItemDataRole.CheckStateRole),
                enabled=bool(self.model().selection_paths(index)),
            )

        clean_option = QStyleOptionViewItem(option)
        clean_option.state &= ~QStyle.StateFlag.State_Selected
        clean_option.state &= ~QStyle.StateFlag.State_MouseOver
        clean_option.state &= ~QStyle.StateFlag.State_HasFocus
        clean_option.showDecorationSelected = False
        clean_option.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
        clean_option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        clean_option.rect = self._content_rect(option, index)
        delegate = self.itemDelegateForIndex(index) or self.itemDelegate()
        if delegate is not None:
            delegate.paint(painter, clean_option, index)

    def set_audio_playback_state(
        self,
        audio_path: Path | None,
        *,
        progress: float,
        is_playing: bool,
        is_paused: bool,
    ) -> None:
        """更新当前试听叶子行的按钮状态与整行进度背景。"""
        self._active_audio_path = Path(audio_path) if audio_path is not None else None
        self._active_audio_progress = max(0.0, min(1.0, float(progress)))
        self._active_audio_is_playing = bool(is_playing and self._active_audio_path)
        self._active_audio_is_paused = bool(is_paused and self._active_audio_path)
        self.viewport().update()


__all__ = [
    "AUDIO_AMBIGUOUS_ROLE",
    "AUDIO_AVAILABLE_ROLE",
    "AUDIO_ID_ROLE",
    "AUDIO_REF_ROLE",
    "EMPTY_MODEL_INDEX",
    "NODE_KIND_ROLE",
    "NODE_LOADED_ROLE",
    "NODE_PAYLOAD_ROLE",
    "PreviewTreeModel",
    "PreviewTreeView",
    "TreeStats",
    "build_tree_summary_text",
    "collect_tree_stats",
]
