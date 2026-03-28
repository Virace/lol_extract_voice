"""测试实体总览页面的显示文案辅助逻辑。"""

from math import dist
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget
from qfluentwidgets import CaptionLabel, LineEdit, Theme, setTheme, setThemeColor, themeColor
from qfluentwidgets import theme as current_theme
from qfluentwidgets.common.color import FluentSystemColor

from lol_audio_unpack.gui.common.styles import (
    get_fluent_frame_stroke_pair,
    get_fluent_neutral_surface_pair,
)
from lol_audio_unpack.gui.components.overview_entity_list import (
    OverviewEntityFilterModel,
    OverviewEntityItemDelegate,
    OverviewEntityListModel,
    OverviewEntityListView,
    _build_overview_interaction_colors,
    build_overview_item_text,
    should_display_overview_row,
)
from lol_audio_unpack.gui.components.overview_status_badge import (
    _build_status_badge_styles,
    _build_status_pill_segment_polygons,
    _build_status_pill_seam_lines,
    _create_status_badge,
    measure_status_pill_width,
    paint_status_pill,
    resolve_status_pill_segment_colors,
)
from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel
from lol_audio_unpack.gui.view.overview_page import (
    OverviewPage,
    build_preview_path_text,
    create_preview_path_edit,
)

EXPECTED_ENTITY_ROW_COUNT = 2
OVERVIEW_LEFT_PANEL_MIN_WIDTH = 280
OVERVIEW_RIGHT_PANEL_MIN_WIDTH = 190
OVERVIEW_BALANCED_SPLITTER_MAX_DELTA = 2
MIN_TRANSPARENT_STATE_RULES = 2
INSET_ZEBRA_MIN_DISTANCE = 6


def _rgba_text(rgba: tuple[int, int, int, int]) -> str:
    """把 token tuple 转成 QSS 中的 rgba 文本。"""
    return f"rgba({rgba[0]}, {rgba[1]}, {rgba[2]}, {rgba[3]})"


def _sample_entity_rows() -> list[dict[str, str]]:
    """构造总览页实体列表的最小样例数据。"""
    return [
        {
            "id": "1",
            "name": "安妮",
            "alias": "Annie",
            "audio": "已存在",
            "mapping": "已存在",
            "mapping_file": "hashes/16.5/champions/1.yml",
            "entity_type": "champions",
        },
        {
            "id": "2",
            "name": "奥拉夫",
            "alias": "Olaf",
            "audio": "未存在",
            "mapping": "未存在",
            "mapping_file": "",
            "entity_type": "champions",
        },
    ]


def test_build_overview_item_text_matches_entity_name() -> None:
    """列表主文案应只展示实体名称。"""
    sample_mapping_path = Path("hashes") / "16.5" / "champions" / "103.json"
    row = {
        "name": "阿狸·九尾妖狐",
        "alias": "Ahri",
        "mapping_file": str(sample_mapping_path),
    }

    assert build_overview_item_text(row) == "阿狸·九尾妖狐"


def test_build_preview_path_text_returns_full_path(tmp_path) -> None:
    """预览区域顶部应直接显示完整路径。"""
    path = tmp_path / "hashes" / "16.5" / "champions" / "103.json"

    assert build_preview_path_text(None) == ""
    assert build_preview_path_text(path) == str(path)


def test_should_display_overview_row_accepts_any_valid_entity_row(tmp_path) -> None:
    """实体总览页展示全部有效实体，不依赖 mapping 状态过滤。"""
    sample_mapping_path = tmp_path / "hashes" / "16.5" / "champions" / "1.json"
    assert should_display_overview_row({"id": "1", "mapping": "已存在", "mapping_file": ""}) is True
    assert should_display_overview_row({"id": "1", "mapping": "未存在", "mapping_file": str(sample_mapping_path)}) is True
    assert should_display_overview_row({"id": "", "mapping": "已存在"}) is False


def test_build_status_badge_styles_switches_foreground_with_theme() -> None:
    """状态徽章应为亮暗主题分别生成不同前景色与底色。"""
    light_qss, dark_qss = _build_status_badge_styles("已存在")

    assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.LIGHT).name() in light_qss.lower()
    assert "color: #FFFFFF;" in light_qss
    assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.DARK).name() in dark_qss.lower()
    assert "color: #111111;" in dark_qss


def test_create_status_badge_updates_with_theme_switch() -> None:
    """状态徽章应注册到主题系统并在切换后刷新样式。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    parent = QWidget()

    try:
        setTheme(Theme.LIGHT)
        badge = _create_status_badge("audio", "已存在", parent)
        assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.LIGHT).name() in badge.styleSheet().lower()
        assert "color: #FFFFFF;" in badge.styleSheet()

        setTheme(Theme.DARK)
        app.processEvents()

        assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.DARK).name() in badge.styleSheet().lower()
        assert "color: #111111;" in badge.styleSheet()
    finally:
        setTheme(original_theme)


def test_create_status_badge_uses_fluent_system_colors() -> None:
    """状态徽章颜色应和 qfluentwidgets 的系统语义色保持一致。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    parent = QWidget()

    try:
        setTheme(Theme.LIGHT)
        success_badge = _create_status_badge("audio", "已存在", parent)
        caution_badge = _create_status_badge("mapping", "未存在", parent)
        app.processEvents()

        assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.LIGHT).name() in success_badge.styleSheet().lower()
        assert FluentSystemColor.CAUTION_FOREGROUND.color(Theme.LIGHT).name() in caution_badge.styleSheet().lower()

        setTheme(Theme.DARK)
        app.processEvents()

        assert FluentSystemColor.SUCCESS_FOREGROUND.color(Theme.DARK).name() in success_badge.styleSheet().lower()
        assert FluentSystemColor.CAUTION_FOREGROUND.color(Theme.DARK).name() in caution_badge.styleSheet().lower()
    finally:
        setTheme(original_theme)


def test_measure_status_pill_width_grows_with_segments_and_label_length() -> None:
    """分段胶囊宽度应随段数和标签长度动态增长。"""
    app = QApplication.instance() or QApplication([])
    metrics = QFontMetrics(app.font())

    width_two = measure_status_pill_width(("A", "M"), metrics)
    width_three = measure_status_pill_width(("A", "M", "X"), metrics)
    width_long = measure_status_pill_width(("Audio", "M"), metrics)

    assert width_two > 0
    assert width_three > width_two
    assert width_long > width_two


def test_build_status_pill_segment_polygons_use_diagonal_split() -> None:
    """分段胶囊的接缝应保留斜切，而不是完全垂直对半。"""
    polygons = _build_status_pill_segment_polygons(
        QRect(0, 0, 72, 24),
        (36, 36),
        diagonal_offset=6,
    )

    assert len(polygons) == 2
    first_points = [polygons[0].at(i) for i in range(polygons[0].count())]
    second_points = [polygons[1].at(i) for i in range(polygons[1].count())]

    assert first_points[1].x() != first_points[2].x()
    assert second_points[0].x() != second_points[3].x()


def test_resolve_status_pill_segment_colors_uses_muted_semantic_palette() -> None:
    """A/M 分段胶囊应使用低饱和的暖色/绿色语义，而不是通用成功警告色。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    widget = QWidget()

    try:
        setTheme(Theme.LIGHT)
        app.processEvents()
        light_palette = widget.palette()
        audio_bg_light, audio_fg_light = resolve_status_pill_segment_colors("A", "已存在", light_palette)
        mapping_bg_light, mapping_fg_light = resolve_status_pill_segment_colors("M", "已存在", light_palette)
        audio_missing_light, _audio_missing_fg_light = resolve_status_pill_segment_colors("A", "未存在", light_palette)

        setTheme(Theme.DARK)
        app.processEvents()
        dark_palette = widget.palette()
        mapping_missing_dark, mapping_missing_fg_dark = resolve_status_pill_segment_colors("M", "未存在", dark_palette)
        audio_bg_dark, _audio_fg_dark = resolve_status_pill_segment_colors("A", "已存在", dark_palette)
        mapping_bg_dark, _mapping_fg_dark = resolve_status_pill_segment_colors("M", "已存在", dark_palette)

        assert audio_bg_light.name() == "#bc8f36"
        assert mapping_bg_light.name() == "#67a85b"
        assert audio_fg_light.name() == "#fffaf1"
        assert mapping_fg_light.name() == "#f7fff5"
        assert audio_missing_light.name() == "#d8c4a0"
        assert mapping_missing_dark.name() == "#4f6950"
        assert mapping_missing_fg_dark.name() == "#d3ebcf"
        assert audio_bg_dark.name() == "#8f6d33"
        assert mapping_bg_dark.name() == "#5a8f56"
    finally:
        setTheme(original_theme)


def test_build_status_pill_seam_lines_match_segment_boundaries_without_gaps() -> None:
    """分段胶囊的斜切分隔线应和接缝重合，并从顶部连到底部。"""
    rect = QRect(0, 0, 72, 24)
    segment_widths = (36, 36)
    seam_lines = _build_status_pill_seam_lines(rect, segment_widths, diagonal_offset=6)

    assert len(seam_lines) == 1
    start, end = seam_lines[0]
    assert start.x() == 39.5
    assert end.x() == 33.5
    assert start.y() == 0.5
    assert end.y() == 23.5


def test_paint_status_pill_keeps_seam_inside_capsule_bounds() -> None:
    """接缝线不应在胶囊顶部外侧留下可见像素。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    image = QImage(84, 36, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    widget = QWidget()

    try:
        setTheme(Theme.LIGHT)
        app.processEvents()
        paint_status_pill(
            painter,
            QRect(6, 6, 72, 24),
            (("A", "已存在"), ("M", "已存在")),
            palette=widget.palette(),
        )
    finally:
        painter.end()
        setTheme(original_theme)

    above_seam = image.pixelColor(45, 5)
    on_seam = image.pixelColor(45, 6)

    assert above_seam.alpha() == 0
    assert on_seam.alpha() > 0


def test_resolve_status_pill_segment_colors_follows_theme_not_widget_palette() -> None:
    """切换 Fluent 主题后，胶囊配色应跟随主题，而不是依赖 QWidget palette 的窗口色。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    widget = QWidget()

    try:
        setTheme(Theme.LIGHT)
        app.processEvents()
        light_palette = widget.palette()
        light_audio_bg, _light_audio_fg = resolve_status_pill_segment_colors("A", "已存在", light_palette)
        light_mapping_bg, _light_mapping_fg = resolve_status_pill_segment_colors("M", "已存在", light_palette)

        setTheme(Theme.DARK)
        app.processEvents()
        dark_palette = widget.palette()
        dark_audio_bg, _dark_audio_fg = resolve_status_pill_segment_colors("A", "已存在", dark_palette)
        dark_mapping_bg, _dark_mapping_fg = resolve_status_pill_segment_colors("M", "已存在", dark_palette)

        assert light_audio_bg.name() == "#bc8f36"
        assert light_mapping_bg.name() == "#67a85b"
        assert dark_audio_bg.name() == "#8f6d33"
        assert dark_mapping_bg.name() == "#5a8f56"
    finally:
        setTheme(original_theme)


def test_overview_interaction_colors_use_theme_accent_and_neutral_surface() -> None:
    """列表交互态应使用中性底色，并让左侧 accent 跟随主题色。"""
    original_theme = current_theme()
    original_color = QColor(themeColor())

    try:
        setTheme(Theme.LIGHT)
        setThemeColor(QColor("#3366FF"))
        hover_bg, selection_bg, accent = _build_overview_interaction_colors()
        assert accent.name() == themeColor().name()
        assert hover_bg.name() != themeColor().name()
        assert selection_bg.name() != themeColor().name()

        setTheme(Theme.DARK)
        setThemeColor(QColor("#FF6A3D"))
        hover_bg, selection_bg, accent = _build_overview_interaction_colors()
        assert accent.name() == themeColor().name()
        assert hover_bg.name() != themeColor().name()
        assert selection_bg.name() != themeColor().name()
    finally:
        setTheme(original_theme)
        setThemeColor(original_color)


def test_create_preview_path_edit_uses_fluent_line_edit() -> None:
    """预览路径输入框应使用 Fluent LineEdit 以跟随主题。"""
    widget = create_preview_path_edit()

    assert isinstance(widget, LineEdit)
    assert widget.isReadOnly() is True


def test_create_preview_path_edit_prefers_shrinking_in_splitter() -> None:
    """预览路径输入框不应强行撑大右侧面板。"""
    widget = create_preview_path_edit()

    assert widget.minimumWidth() == 0
    assert widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored


def test_overview_page_uses_polished_preview_copy() -> None:
    """总览页右侧预览区文案应避免开发阶段的占位措辞。"""
    QApplication.instance() or QApplication([])
    page = OverviewPage()
    caption_texts = {label.text() for label in page.findChildren(CaptionLabel)}

    assert create_preview_path_edit().placeholderText() == "请选择左侧实体以查看原始数据。"
    assert page.text_preview.toPlainText() == "请选择左侧实体以查看原始数据。"
    assert page._audio_preview_placeholder == "请选择左侧实体以查看事件内容。"
    assert "右侧可以查看当前实体的事件和原始数据。" in caption_texts
    assert page.audio_preview_summary_label.text() == "这里会显示当前实体的事件分组、类型和音频数量。"


def test_overview_page_entity_list_uses_virtualized_model_view_pipeline() -> None:
    """左侧实体列表应改为 model/view + delegate 的虚拟化结构。"""
    page = OverviewPage()
    page.set_entity_data("champions", _sample_entity_rows())

    view = page._entity_lists["champions"]
    proxy_model = view.model()

    assert isinstance(view, OverviewEntityListView)
    assert isinstance(view.itemDelegate(), OverviewEntityItemDelegate)
    assert isinstance(proxy_model, OverviewEntityFilterModel)
    assert isinstance(proxy_model.sourceModel(), OverviewEntityListModel)
    assert proxy_model.rowCount() == EXPECTED_ENTITY_ROW_COUNT
    assert view.indexWidget(proxy_model.index(0, 0)) is None
    assert hasattr(view, "scrollDelegate")


def test_overview_page_entity_list_applies_theme_styles() -> None:
    """左侧实体列表应有和 Fluent 页面一致的主题样式。"""
    page = OverviewPage()
    style_sheet = page._entity_lists["champions"].styleSheet()

    assert "QListView" in style_sheet
    assert "QListView::item:hover" in style_sheet
    assert "QListView::item:selected" in style_sheet
    assert style_sheet.count("background-color: transparent;") >= MIN_TRANSPARENT_STATE_RULES
    assert "border: none;" in style_sheet


def test_overview_page_selection_cards_follow_theme_tokens() -> None:
    """总览页选择条与摘要卡片应随主题切换到对应的中性 surface 与描边 token。"""
    app = QApplication.instance() or QApplication([])
    original_theme = current_theme()
    selection_bar_background = get_fluent_neutral_surface_pair("subtle_idle")
    selection_bar_border = get_fluent_frame_stroke_pair()

    try:
        page = OverviewPage()
        selection_bar = page.findChild(QWidget, "OverviewSelectionBar")
        assert selection_bar is not None

        setTheme(Theme.LIGHT)
        app.processEvents()
        assert _rgba_text(selection_bar_background[0]) in selection_bar.styleSheet()
        assert selection_bar_border[0] in selection_bar.styleSheet()
        assert _rgba_text(selection_bar_background[0]) in page.audio_preview_summary_card.styleSheet()
        assert selection_bar_border[0] in page.audio_preview_summary_card.styleSheet()

        setTheme(Theme.DARK)
        app.processEvents()
        assert _rgba_text(selection_bar_background[1]) in selection_bar.styleSheet()
        assert selection_bar_border[1] in selection_bar.styleSheet()
        assert _rgba_text(selection_bar_background[1]) in page.audio_preview_summary_card.styleSheet()
        assert selection_bar_border[1] in page.audio_preview_summary_card.styleSheet()
    finally:
        setTheme(original_theme)


def test_overview_page_entity_list_uses_inset_zebra_surface_for_idle_rows(qtbot) -> None:
    """普通斑马行应只在内层交互区域着色，而不是整块方角灰底贴边。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    qtbot.addWidget(page)
    page.resize(640, 520)
    page.set_entity_data("champions", _sample_entity_rows())
    page.show()
    app.processEvents()

    view = page._entity_lists["champions"]
    index = view.model().index(1, 0)
    row_rect = view.visualRect(index)
    image = view.viewport().grab().toImage()
    dpr = image.devicePixelRatio()
    outer_x = round((row_rect.left() + 1) * dpr)
    inner_x = round((row_rect.left() + 12) * dpr)
    sample_y = round(row_rect.center().y() * dpr)

    outer_pixel = image.pixelColor(outer_x, sample_y)
    inner_pixel = image.pixelColor(inner_x, sample_y)
    outer_rgba = (outer_pixel.red(), outer_pixel.green(), outer_pixel.blue(), outer_pixel.alpha())
    inner_rgba = (inner_pixel.red(), inner_pixel.green(), inner_pixel.blue(), inner_pixel.alpha())

    assert view.alternatingRowColors() is False
    assert dist(outer_rgba, inner_rgba) >= INSET_ZEBRA_MIN_DISTANCE


def test_overview_page_search_filters_proxy_row_count() -> None:
    """搜索框应通过代理模型收窄当前可见行数，而不是仅隐藏旧 item。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    page.nav_pivot.setCurrentItem("maps")
    page.set_entity_data(
        "maps",
        [
            {
                "id": "11",
                "name": "召唤师峡谷",
                "alias": "Map11",
                "audio": "已存在",
                "mapping": "已存在",
                "mapping_file": "hashes/16.5/maps/11.yml",
                "entity_type": "maps",
            },
            {
                "id": "12",
                "name": "嚎哭深渊",
                "alias": "Map12",
                "audio": "未存在",
                "mapping": "已存在",
                "mapping_file": "hashes/16.5/maps/12.yml",
                "entity_type": "maps",
            },
        ],
    )

    page.search_input.setText("嚎哭")
    app.processEvents()

    assert page._entity_lists["maps"].model().rowCount() == 1


def test_overview_page_splitter_defaults_to_adaptive_ratio(qtbot) -> None:
    """未选择实体时左右面板应默认保持近似对称。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    qtbot.wait(10)

    left_size, right_size = page.splitter.sizes()

    assert abs(left_size - right_size) <= OVERVIEW_BALANCED_SPLITTER_MAX_DELTA
    assert left_size >= OVERVIEW_LEFT_PANEL_MIN_WIDTH
    assert right_size >= OVERVIEW_RIGHT_PANEL_MIN_WIDTH


def test_overview_page_defaults_preview_mode_to_event_tab() -> None:
    """右侧切换条应把事件视图放在前面，并默认选中事件。"""
    page = OverviewPage()

    assert page.preview_mode_pivot.currentRouteKey() == "audio"
    assert page.preview_mode_pivot.currentItem().text() == "事件"


def test_overview_page_header_and_splitter_use_single_line_and_locked_handle() -> None:
    """副标题应保持单行，左右区域中间句柄默认不允许拖动。"""
    page = OverviewPage()

    assert page.subtitle_label.wordWrap() is False
    assert page.subtitle_label.text() == "查看英雄和地图状态，选好后可直接发送到执行中心。"
    assert page.splitter.handleWidth() == 0
    assert page.splitter.handle(1).isEnabled() is False
    assert page.sync_selection_btn.text() == "发送到执行中心"


def test_overview_page_splitter_shrinks_with_window_width(qtbot) -> None:
    """窗口缩小时左侧列表宽度也应跟着收缩，而不是保持过宽。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    qtbot.wait(10)

    initial_left, _initial_right = page.splitter.sizes()
    page.resize(760, 800)
    qtbot.wait(10)
    shrunk_left, shrunk_right = page.splitter.sizes()

    assert shrunk_left < initial_left
    assert shrunk_left >= OVERVIEW_LEFT_PANEL_MIN_WIDTH
    assert shrunk_right >= OVERVIEW_RIGHT_PANEL_MIN_WIDTH


def test_overview_page_empty_selection_uses_shorter_status_text() -> None:
    """未选择实体时顶部应显示计数摘要，底部操作栏不再承载提示文本。"""
    page = OverviewPage()

    assert page.selection_status_label.text() == "已选 0 个英雄，0 张地图。"
    assert page.selection_status_label.parentWidget() is not page.selection_bar


def test_overview_page_selected_payload_summary_guides_next_step() -> None:
    """同步到执行中心前的摘要应直接告诉用户已选内容和下一步。"""
    page = OverviewPage()
    page._selected_entity_ids["champions"].update({"1", "103"})
    page._selected_entity_ids["maps"].add("11")

    payload = page._selected_payload()

    assert payload["summary"] == "已选择 2 个英雄、1 张地图，请前往执行中心继续创建任务。"


def test_overview_page_load_preview_populates_audio_tree_and_summary(tmp_path) -> None:
    """加载预览后应同步更新 Raw 文本、试听树与摘要信息。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.yml"
    page._loader = Mock()
    page._loader.data_reader = Mock()
    page._loader.data_reader.get_champion.return_value = {
        "skins": [
            {
                "id": 1000,
                "skinNames": {
                    "zh_CN": "基础皮肤",
                },
            }
        ]
    }
    page._loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "1000": {
                    "events": {
                        "Annie_Base_VO": {
                            "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                        }
                    }
                }
            }
        },
        "raw-preview",
    )
    page._loader.load_available_audio_ids.return_value = {"118669424"}
    item = Mock()
    item.data.return_value = {
        "id": "1",
        "name": "安妮",
    }

    page._load_preview_for_item("champions", item)
    app.processEvents()

    assert isinstance(page.preview_path_edit, LineEdit)
    assert page.preview_path_edit.text() == str(preview_path)
    assert page.text_preview.toPlainText() == "raw-preview"
    assert page.audio_preview_summary_label.text() == "分组 1 · 类型 1 · 事件 1 · ID 2 · 可试听 1"
    model = page.audio_preview_tree.model()
    assert isinstance(model, PreviewTreeModel)
    assert page.audio_preview_tree.styleSheet() != ""
    assert hasattr(page.audio_preview_tree, "audio_id_requested") is False
    assert model.rowCount() == 1

    skin_index = model.index(0, 0)
    assert model.data(skin_index, Qt.DisplayRole) == "基础皮肤"
    model.ensure_children_loaded(skin_index)
    type_index = model.index(0, 0, skin_index)
    assert model.data(type_index, Qt.DisplayRole) == "Annie_Base_VO"
    model.ensure_children_loaded(type_index)
    event_index = model.index(0, 0, type_index)
    assert model.data(event_index, Qt.DisplayRole) == "Play_vo_Annie_Attack2DGeneral"
    model.ensure_children_loaded(event_index)
    id_index = model.index(0, 0, event_index)
    unavailable_index = model.index(1, 0, event_index)
    assert model.data(id_index, Qt.DisplayRole) == "118669424"
    assert model.data(unavailable_index, Qt.DisplayRole) == "223585177"


def test_overview_page_audio_preview_tree_uses_custom_preview_tree_styles() -> None:
    """总览页右侧应挂载保持自定义样式的试听树控件。"""
    page = OverviewPage()

    assert isinstance(page.audio_preview_tree.model(), PreviewTreeModel)
    assert page.audio_preview_tree.styleSheet() != ""
    assert hasattr(page.audio_preview_tree, "audio_id_requested") is False


def test_overview_page_load_map_preview_populates_audio_tree_and_summary(tmp_path) -> None:
    """地图预览应能像英雄一样驱动 Raw、试听树与摘要。"""
    app = QApplication.instance() or QApplication([])
    page = OverviewPage()
    preview_path = tmp_path / "hashes" / "16.5" / "maps" / "11.yml"
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "map": {
                "11": {
                    "events": {
                        "Map11_Music": {
                            "Play_map_theme": [7654321, 7654322],
                        }
                    }
                }
            }
        },
        "map-raw-preview",
    )
    page._loader.load_available_audio_ids.return_value = {"7654321"}
    item = Mock()
    item.data.return_value = {
        "id": "11",
        "name": "召唤师峡谷",
    }

    page._load_preview_for_item("maps", item)
    app.processEvents()

    assert page.preview_path_edit.text() == str(preview_path)
    assert page.text_preview.toPlainText() == "map-raw-preview"
    assert page.audio_preview_summary_label.text() == "分组 1 · 类型 1 · 事件 1 · ID 2 · 可试听 1"

    model = page.audio_preview_tree.model()
    assert isinstance(model, PreviewTreeModel)
    root_index = model.index(0, 0)
    assert model.data(root_index, Qt.DisplayRole) == "11"
    model.ensure_children_loaded(root_index)
    type_index = model.index(0, 0, root_index)
    assert model.data(type_index, Qt.DisplayRole) == "Map11_Music"
    model.ensure_children_loaded(type_index)
    event_index = model.index(0, 0, type_index)
    assert model.data(event_index, Qt.DisplayRole) == "Play_map_theme"
    model.ensure_children_loaded(event_index)
    available_index = model.index(0, 0, event_index)
    unavailable_index = model.index(1, 0, event_index)

    assert model.data(available_index, Qt.DisplayRole) == "7654321"
    assert model.data(unavailable_index, Qt.DisplayRole) == "7654322"


def test_overview_page_preview_load_keeps_left_list_without_horizontal_scroll(qtbot, tmp_path) -> None:
    """载入右侧预览后，左侧列表仍不应出现水平滚动条。"""
    page = OverviewPage()
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.set_entity_data("champions", _sample_entity_rows())
    page.show()
    qtbot.wait(10)

    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.msgpack"
    page._loader = Mock()
    page._loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "1000": {
                    "events": {
                        "Annie_Base_VO": {
                            "Play_vo_Annie_Attack2DGeneral": [118669424, 223585177],
                        }
                    }
                }
            }
        },
        "{\n  \"metadata\": \"" + ("x" * 4000) + "\"\n}",
    )
    page._loader.load_available_audio_ids.return_value = {"118669424"}

    index = page._entity_lists["champions"].model().index(0, 0)
    page._load_preview_for_item("champions", index)
    qtbot.wait(10)

    view = page._entity_lists["champions"]
    left_size, right_size = page.splitter.sizes()

    assert hasattr(view, "scrollDelegate")
    assert view.horizontalScrollBar().maximum() == 0
    assert left_size >= OVERVIEW_LEFT_PANEL_MIN_WIDTH
    assert right_size >= OVERVIEW_RIGHT_PANEL_MIN_WIDTH
