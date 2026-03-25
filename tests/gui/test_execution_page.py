"""测试执行中心日志面板同步逻辑。"""

from loguru import logger
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QWidget

import lol_audio_unpack.gui.view.execution_page as execution_page_module
from lol_audio_unpack.gui.common import (
    clear_buffered_log_lines,
    install_startup_log_buffer,
    remove_startup_log_buffer,
)
from lol_audio_unpack.gui.common.loguru_palette import ANSI_FIXED_HEX_BY_SGR
from lol_audio_unpack.gui.components.log_drawer import (
    LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT,
    LOG_PANEL_HANDLE_SIZE,
    LOG_PANEL_MAX_HEIGHT,
    LOG_PANEL_MIN_HEIGHT,
    LOG_PANEL_MIN_TOP_GAP,
    LOG_PANEL_SIDE_MARGIN,
    LOG_PANEL_TOP_MARGIN,
    GlobalLogDrawer,
    _build_log_panel_geometry,
    _build_log_panel_host_rect,
    _build_log_panel_toggle_rect,
    _resolve_log_panel_height,
)
from lol_audio_unpack.gui.task_models import ExecutionTaskProgress, ExecutionTaskResult
from lol_audio_unpack.gui.view.execution_page import ExecutionPage


def test_execution_page_preloads_buffered_startup_logs() -> None:
    """执行中心初始化时应带上启动期已缓冲的日志。"""
    app = QApplication.instance() or QApplication([])
    clear_buffered_log_lines()
    install_startup_log_buffer()

    try:
        logger.info("GUI 启动前置日志")
        page = ExecutionPage()
        app.processEvents()

        assert "GUI 启动前置日志" in page.current_log_text()
        page.deleteLater()
        app.processEvents()
    finally:
        remove_startup_log_buffer()
        clear_buffered_log_lines()


def test_execution_page_attaches_real_runtime_logs_to_buffer() -> None:
    """执行中心应能接收真实 loguru 输出并落入累计日志文本。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    batches: list[tuple[str, ...]] = []
    page.log_lines_appended.connect(batches.append)
    page.attach_runtime_log_sink()

    logger.info("GUI 日志桥接测试")
    app.processEvents()

    assert batches
    assert any("GUI 日志桥接测试" in line for batch in batches for line in batch)
    assert "GUI 日志桥接测试" in page.current_log_text()
    page.deleteLater()
    app.processEvents()


def test_execution_page_batches_runtime_logs_before_render() -> None:
    """高频运行时日志应先合批，再增量推送给主窗口抽屉。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    batches: list[tuple[str, ...]] = []
    page.log_lines_appended.connect(batches.append)

    page._queue_runtime_log_line("[测试] 第一条运行时日志")
    page._queue_runtime_log_line("[测试] 第二条运行时日志")
    app.processEvents()

    assert batches == [
        ("[测试] 第一条运行时日志", "[测试] 第二条运行时日志"),
    ]
    assert page.current_log_text().endswith("[测试] 第二条运行时日志")
    page.deleteLater()
    app.processEvents()


def test_execution_page_uses_single_task_builder_instead_of_dual_cards() -> None:
    """执行中心应收敛成单任务入口，并用复选项组合执行步骤。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.resize(1130, 800)
    page.show()
    app.processEvents()

    assert hasattr(page, "task_builder_card")
    assert hasattr(page, "progress_card")
    assert hasattr(page, "create_task_btn")
    assert hasattr(page, "extract_task_cb")
    assert hasattr(page, "mapping_task_cb")
    assert hasattr(page, "copy_cli_btn")
    assert not hasattr(page, "extract_card")
    assert not hasattr(page, "mapping_card")
    assert page.extract_task_cb.isChecked() is True
    assert page.mapping_task_cb.isChecked() is True
    assert page.bp_voice_cb.isChecked() is True
    assert page.advanced_card.isExpand is True
    assert page.draft_list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    assert not hasattr(page, "use_synced_selection_cb")
    assert page.copy_cli_btn.text() == "复制 CLI 命令"
    assert page.task_builder_summary_label.text() == "当前会创建：音频解包 + 事件映射。"
    assert page.target_summary_value.text() == "全部英雄+地图"
    assert type(page.target_title_label) is type(page.task_kind_title_label)
    assert type(page.target_summary_value) is type(page.task_builder_summary_label)
    assert page.progress_card.geometry().left() < page.task_builder_card.geometry().left()
    assert page.progress_card.geometry().top() == page.task_builder_card.geometry().top()
    width_delta = abs(page.progress_card.width() - page.task_builder_card.width())
    assert width_delta <= max(page.width() // 50, 1)
    assert page.progress_card.height() == page.task_builder_card.height()
    assert hasattr(page, "bottom_spacing_widget")
    assert page.bottom_spacing_widget.height() > 0

    page.deleteLater()
    app.processEvents()


def test_execution_page_task_queue_keeps_bottom_outer_margin() -> None:
    """任务队列列表并入进度卡片后仍应保持固定高度。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    app.processEvents()

    assert page.draft_list.minimumHeight() > 0
    assert page.draft_list.minimumHeight() == page.draft_list.maximumHeight()
    row_height = page.draft_list.sizeHintForRow(0)
    assert row_height > 0
    expected_height = row_height * 3 + page.draft_list.frameWidth() * 2 + 2
    assert page.draft_list.height() == expected_height

    page.deleteLater()
    app.processEvents()


def test_execution_page_can_copy_full_cli_command() -> None:
    """复制按钮应输出与当前配置一致的 CLI 命令。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.attach_runtime_log_sink()
    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    page.force_update_cb.setChecked(True)
    page.bp_voice_cb.setChecked(False)
    page.integrate_data_cb.setChecked(True)
    page.max_workers_combo.setCurrentText("8")
    app.processEvents()

    page._copy_cli_command()
    app.processEvents()

    expected = (
        "uv run unpack "
        "--update-champions 1,103 --update-maps 11 --force "
        "--extract-champions 1,103 --extract-maps 11 "
        "--mapping-champions 1,103 --mapping-maps 11 "
        "--max-workers 8 --no-with-bp-vo --exclude-type SFX,MUSIC --integrate-data"
    )
    assert QApplication.clipboard().text() == expected
    assert "[CLI] 已复制命令：" in page.current_log_text()

    page.deleteLater()
    app.processEvents()


def test_execution_page_can_merge_synced_selection_with_manual_input() -> None:
    """总览同步遇到已有输入时，应支持合并现有 ID。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    page._ask_sync_conflict_resolution = lambda **_kwargs: "merge"  # type: ignore[method-assign]
    app.processEvents()

    page.set_selected_entities(
        {
            "champion_ids": ("103", "222"),
            "map_ids": ("11", "12"),
            "summary": "实体总览选中了 2 个英雄和 2 张地图",
        }
    )
    app.processEvents()

    assert page.champion_ids_input.text() == "1,103,222"
    assert page.map_ids_input.text() == "11,12"
    assert page.target_summary_value.text() == "目标：英雄 3 个，地图 2 个"

    page.deleteLater()
    app.processEvents()


def test_execution_page_can_cancel_synced_selection_when_conflict_exists() -> None:
    """总览同步遇到冲突且用户取消时，应保留当前输入。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.attach_runtime_log_sink()
    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    page._ask_sync_conflict_resolution = lambda **_kwargs: "cancel"  # type: ignore[method-assign]
    app.processEvents()

    page.set_selected_entities(
        {
            "champion_ids": ("222",),
            "map_ids": ("12",),
            "summary": "实体总览选中了新的目标",
        }
    )
    app.processEvents()

    assert page.champion_ids_input.text() == "1,103"
    assert page.map_ids_input.text() == "11"
    assert page.target_summary_value.text() == "目标：英雄 2 个，地图 1 个"
    assert "[同步] 已取消从实体总览同步选择。" in page.current_log_text()

    page.deleteLater()
    app.processEvents()


def test_execution_page_builds_task_model_from_checkbox_selection(monkeypatch) -> None:
    """创建任务时应生成正式任务模型，并让首项进入运行态。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.attach_runtime_log_sink()
    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    page.force_update_cb.setChecked(True)
    page.bp_voice_cb.setChecked(False)
    page.integrate_data_cb.setChecked(True)
    started_tasks = []

    def capture_started_task(task) -> None:
        started_tasks.append(task)

    monkeypatch.setattr(page, "_start_task_worker", capture_started_task)
    app.processEvents()

    page._queue_task_draft()
    app.processEvents()

    assert len(started_tasks) == 1
    queued_task = started_tasks[0]
    assert queued_task.draft.champion_ids == (1, 103)
    assert queued_task.draft.map_ids == (11,)
    assert queued_task.draft.run_update is True
    assert queued_task.draft.run_extract is True
    assert queued_task.draft.run_mapping is True
    assert queued_task.draft.with_bp_vo is False
    assert queued_task.draft.integrate_data is True
    assert page.draft_list.count() == 1
    row_text = page.draft_list.item(0).text()
    assert "[运行中]" in row_text
    assert "音频解包 + 事件映射" in row_text
    assert "目标：英雄 2 个，地图 1 个" in row_text
    assert "任务队列：1 条" in page.queue_progress_label.text()
    assert "运行中 1" in page.queue_progress_label.text()
    assert "任务已加入队列" in page.task_status_label.text()
    assert page.champion_ids_input.text() == ""
    assert page.map_ids_input.text() == ""
    assert page.target_summary_value.text() == "全部英雄+地图"
    assert page.force_update_cb.isChecked() is False
    assert page.integrate_data_cb.isChecked() is False
    assert page.bp_voice_cb.isChecked() is True
    assert "[队列] #1" in page.current_log_text()

    page.deleteLater()
    app.processEvents()


def test_execution_page_can_remove_waiting_task_without_touching_running_task(monkeypatch) -> None:
    """右键菜单删除等待中的任务时，不应影响已经运行中的任务。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    page.attach_runtime_log_sink()
    monkeypatch.setattr(page, "_start_task_worker", lambda task: None)
    app.processEvents()

    page._queue_task_draft()
    page._queue_task_draft()
    app.processEvents()

    first_item = page.draft_list.item(0)
    second_item = page.draft_list.item(1)
    assert "[运行中]" in first_item.text()
    assert "[等待中]" in second_item.text()

    page._remove_task_item(second_item)
    app.processEvents()

    assert page.draft_list.count() == 1
    assert "[运行中]" in first_item.text()
    assert "运行中 1" in page.queue_progress_label.text()
    assert "等待中 0" in page.queue_progress_label.text()
    assert "[队列] 已移出任务：" in page.current_log_text()

    page.deleteLater()
    app.processEvents()


def test_execution_page_renders_stage_progress_details(monkeypatch) -> None:
    """运行中任务应展示当前阶段、实体类型与当前/总数。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    monkeypatch.setattr(page, "_start_task_worker", lambda task: None)
    page.champion_ids_input.setText("1,103")
    app.processEvents()

    page._queue_task_draft()
    app.processEvents()

    item = page.draft_list.item(0)
    payload = item.data(execution_page_module.TASK_ITEM_ROLE)
    page._on_task_progress(
        payload.task_id,
        ExecutionTaskProgress(
            stage_key="extract",
            stage_label="音频解包",
            entity_scope_label="英雄",
            current=1,
            total=2,
            message="Annie 解包完成",
        ),
    )
    app.processEvents()

    assert page.task_status_label.text() == "当前阶段：音频解包 · 英雄"
    assert page.task_progress_note.text() == "音频解包 · 英雄 · 1/2 · Annie 解包完成"
    expected_total = 2
    assert page.task_progress_bar.maximum() == expected_total
    assert page.task_progress_bar.value() == 1

    page.deleteLater()
    app.processEvents()


def test_execution_page_shows_infobar_after_extract_stage_finishes(monkeypatch) -> None:
    """解包阶段结束后应弹出全局 InfoBar 通知。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    info_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(page, "_start_task_worker", lambda task: None)
    monkeypatch.setattr(
        execution_page_module.InfoBar,
        "info",
        lambda title, content, **_kwargs: info_calls.append((title, content)),
    )
    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    app.processEvents()

    page._queue_task_draft()
    app.processEvents()

    item = page.draft_list.item(0)
    payload = item.data(execution_page_module.TASK_ITEM_ROLE)
    page._on_task_progress(
        payload.task_id,
        ExecutionTaskProgress(
            stage_key="extract",
            stage_label="音频解包",
            entity_scope_label="英雄 + 地图",
            current=1,
            total=1,
            message="音频解包阶段已结束",
            stage_finished=True,
        ),
    )
    app.processEvents()

    assert info_calls == [("音频解包阶段已结束", f"任务 #{payload.task_id} 已结束音频解包阶段。 正在继续事件映射。")]

    page.deleteLater()
    app.processEvents()


def test_execution_page_marks_task_completed_after_worker_finishes(monkeypatch) -> None:
    """首个任务完成后应写回完成状态并触发数据刷新请求。"""
    app = QApplication.instance() or QApplication([])
    page = ExecutionPage()
    refresh_events: list[bool] = []
    page.refresh_requested.connect(lambda: refresh_events.append(True))

    class _ImmediateThreadPool:
        def start(self, worker) -> None:
            worker.run()

    def fake_global_instance() -> _ImmediateThreadPool:
        return _ImmediateThreadPool()

    def fake_run_execution_task(task, signals) -> ExecutionTaskResult:
        signals.progress.emit(
            ExecutionTaskProgress(
                stage_key="extract",
                stage_label="音频解包",
                entity_scope_label="英雄",
                current=2,
                total=2,
                message="英雄解包完成",
            )
        )
        signals.progress.emit(
            ExecutionTaskProgress(
                stage_key="mapping",
                stage_label="事件映射",
                entity_scope_label="地图",
                current=1,
                total=1,
                message="地图映射完成",
            )
        )
        return ExecutionTaskResult(
            completed_steps=("音频解包", "事件映射"),
            summary="已完成：音频解包 -> 事件映射（1.2s）",
            duration_seconds=1.2,
        )

    monkeypatch.setattr(execution_page_module, "run_execution_task", fake_run_execution_task)
    monkeypatch.setattr(
        execution_page_module.QThreadPool,
        "globalInstance",
        staticmethod(fake_global_instance),
    )

    page.champion_ids_input.setText("1,103")
    page.map_ids_input.setText("11")
    app.processEvents()

    page._queue_task_draft()
    app.processEvents()

    assert page.draft_list.count() == 1
    assert "[已完成]" in page.draft_list.item(0).text()
    assert "已完成 1" in page.queue_progress_label.text()
    assert page.task_progress_note.text().startswith("100%")
    assert refresh_events == [True]

    page.deleteLater()
    app.processEvents()


def test_global_log_drawer_keeps_appending_while_collapsed() -> None:
    """日志抽屉在隐藏状态下也应持续追加文本并保持滚动到底部。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_expanded(False, animate=False)

    drawer.append_log_lines(("[测试] 抽屉隐藏中持续渲染", "[测试] 多日志批量追加完成"))
    app.processEvents()

    output = drawer.output_widget.toPlainText()
    scrollbar = drawer.output_widget.verticalScrollBar()
    assert "[测试] 抽屉隐藏中持续渲染" in output
    assert output.endswith("[测试] 多日志批量追加完成")
    assert scrollbar.value() == scrollbar.maximum()
    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_created_after_host_show_keeps_toggle_visible() -> None:
    """宿主已显示后再创建抽屉时，折叠态入口按钮也应立即可见。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    host.show()
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_expanded(False, animate=False)
    app.processEvents()

    assert drawer._toggle_btn.isVisible()

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_follow_scroll_switch_defaults_to_enabled() -> None:
    """日志抽屉默认应保持跟随最新日志滚动。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    assert drawer._follow_scroll_switch.isChecked()
    assert drawer._follow_output_scroll is True

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_can_disable_follow_scroll() -> None:
    """关闭保持滚动后，新日志不应强制把滚动条拖回底部。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    drawer.set_log_text("\n".join(f"[测试] 初始日志 {i}" for i in range(600)))
    app.processEvents()

    scrollbar = drawer.output_widget.verticalScrollBar()
    assert scrollbar.maximum() > 0

    drawer.set_follow_scroll_enabled(False)
    scrollbar.setValue(0)
    drawer.append_log_lines(("[测试] 新增日志 A", "[测试] 新增日志 B"))
    app.processEvents()

    assert drawer._follow_scroll_switch.isChecked() is False
    assert scrollbar.value() == 0

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_backdrop_respects_auto_collapse_setting() -> None:
    """蒙版应在展开时出现，并根据设置决定是否拦截外部点击。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    host.show()
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_expanded(True, animate=False)
    app.processEvents()

    assert drawer._backdrop.isVisible()
    assert drawer._backdrop.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is False

    drawer.set_auto_collapse_enabled(False)
    app.processEvents()

    assert drawer._backdrop.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_backdrop_click_collapses_panel() -> None:
    """启用自动收起时，点击蒙版应收起日志抽屉。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    host.show()
    drawer = GlobalLogDrawer(host)
    drawer.sync_host_rect(_build_log_panel_host_rect(host.size(), navigation_width=48), animate=False)
    drawer.set_auto_collapse_enabled(True)
    drawer.set_expanded(True, animate=False)
    app.processEvents()

    drawer._backdrop.clicked.emit()
    app.processEvents()

    assert drawer._expanded is False
    assert drawer._backdrop.isVisible() is False

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_backdrop_keeps_lightweight_refresh_entry() -> None:
    """日志蒙版应保留轻量刷新入口，且不依赖实时 Qt 模糊效果。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    drawer._backdrop.refresh_snapshot()
    app.processEvents()

    assert not hasattr(drawer._backdrop, "_snapshot_label")

    host.deleteLater()
    app.processEvents()


def test_global_log_drawer_stylesheet_contains_theme_text_color() -> None:
    """日志抽屉正文样式应显式声明前景色。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    assert "color:" in drawer.output_widget.styleSheet()

    host.deleteLater()
    app.processEvents()


def test_log_drawer_highlighter_uses_level_color_for_message() -> None:
    """级别颜色应同时作用于级别字段和消息正文，INFO 保持正文默认色。"""
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1130, 800)
    drawer = GlobalLogDrawer(host)
    app.processEvents()

    base_color = drawer._highlighter._base_format.foreground().color()
    info_level_color = drawer._highlighter._level_formats["INFO"].foreground().color()
    info_message_color = drawer._highlighter._message_formats["INFO"].foreground().color()
    error_level_color = drawer._highlighter._level_formats["ERROR"].foreground().color()
    error_message_color = drawer._highlighter._message_formats["ERROR"].foreground().color()
    debug_level_color = drawer._highlighter._level_formats["DEBUG"].foreground().color()
    warning_level_color = drawer._highlighter._message_formats["WARNING"].foreground().color()
    critical_background = drawer._highlighter._message_formats["CRITICAL"].background().color()

    assert info_level_color == info_message_color
    assert info_message_color == base_color
    assert error_level_color == error_message_color
    assert error_message_color != info_message_color
    assert debug_level_color.name() == ANSI_FIXED_HEX_BY_SGR[34].lower()
    assert warning_level_color.name() == ANSI_FIXED_HEX_BY_SGR[33].lower()
    assert critical_background.name() == ANSI_FIXED_HEX_BY_SGR[41].lower()

    host.deleteLater()
    app.processEvents()


def test_log_panel_geometry_stays_inside_content_area() -> None:
    """日志抽屉展开时应停靠底部，收起时应整体滑出内容区。"""
    host_rect = _build_log_panel_host_rect(QSize(1130, 800), navigation_width=48)

    collapsed = _build_log_panel_geometry(host_rect, expanded=False)
    expanded = _build_log_panel_geometry(host_rect, expanded=True)

    assert collapsed.height() == expanded.height()
    assert collapsed.left() == host_rect.left()
    assert expanded.left() == host_rect.left()
    assert collapsed.right() == host_rect.right()
    assert expanded.right() == host_rect.right()
    assert expanded.bottom() == host_rect.bottom()
    assert collapsed.top() == host_rect.bottom() + 1


def test_log_panel_geometry_respects_height_cap_for_large_window() -> None:
    """窗口较高时日志面板仍应受到最大高度限制。"""
    host_rect = _build_log_panel_host_rect(QSize(1440, 1600), navigation_width=64)

    expanded = _build_log_panel_geometry(host_rect, expanded=True)
    collapsed = _build_log_panel_geometry(host_rect, expanded=False)

    assert expanded.height() == collapsed.height()
    assert expanded.height() < host_rect.height() // 2
    assert expanded.top() > host_rect.top()
    assert collapsed.top() > host_rect.bottom()


def test_resolve_log_panel_height_clamps_default_and_dragged_height() -> None:
    """日志抽屉高度应同时遵守默认上限和拖拽后的窗口上限。"""
    host_rect = _build_log_panel_host_rect(QSize(1440, 1000), navigation_width=64)

    default_height = _resolve_log_panel_height(host_rect)
    dragged_height = _resolve_log_panel_height(host_rect, preferred_height=9999)
    expected_max_height = host_rect.height() - LOG_PANEL_TOP_MARGIN - LOG_PANEL_MIN_TOP_GAP

    assert LOG_PANEL_MIN_HEIGHT <= default_height <= LOG_PANEL_MAX_HEIGHT
    assert dragged_height == expected_max_height


def test_log_panel_toggle_rect_respects_collapsed_hover_only() -> None:
    """收起时按钮停靠右下角，悬停会上浮；展开态不再应用悬停动画。"""
    host_rect = _build_log_panel_host_rect(QSize(1130, 800), navigation_width=48)
    collapsed_panel = _build_log_panel_geometry(host_rect, expanded=False)
    expanded_panel = _build_log_panel_geometry(host_rect, expanded=True)

    collapsed_toggle = _build_log_panel_toggle_rect(
        host_rect,
        collapsed_panel,
        expanded=False,
        hovered=False,
    )
    hovered_toggle = _build_log_panel_toggle_rect(
        host_rect,
        collapsed_panel,
        expanded=False,
        hovered=True,
    )
    expanded_toggle = _build_log_panel_toggle_rect(
        host_rect,
        expanded_panel,
        expanded=True,
        hovered=False,
    )
    expanded_hovered_toggle = _build_log_panel_toggle_rect(
        host_rect,
        expanded_panel,
        expanded=True,
        hovered=True,
    )

    assert collapsed_toggle.width() == LOG_PANEL_HANDLE_SIZE
    assert collapsed_toggle.height() == LOG_PANEL_HANDLE_SIZE
    assert collapsed_toggle.right() == host_rect.right() - LOG_PANEL_SIDE_MARGIN
    assert collapsed_toggle.top() == collapsed_panel.top() - LOG_PANEL_COLLAPSED_VISIBLE_HEIGHT
    assert collapsed_toggle.bottom() > host_rect.bottom()
    assert hovered_toggle.top() < collapsed_toggle.top()
    assert expanded_toggle.top() == expanded_panel.top() - LOG_PANEL_HANDLE_SIZE // 2
    assert expanded_toggle.right() <= expanded_panel.right()
    assert expanded_hovered_toggle == expanded_toggle
