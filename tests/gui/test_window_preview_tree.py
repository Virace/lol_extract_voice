"""测试主窗口宿主中的基础预览树。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

import lol_audio_unpack.gui.__main__ as gui_main_module
import lol_audio_unpack.gui.view.execution_page as execution_page_module
import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.gui.components.preview_tree import PreviewTreeModel
from lol_audio_unpack.gui.task_models import ExecutionTaskResult
from lol_audio_unpack.gui.window import MainWindow


def _configure_gui_app(app: QApplication, *, theme: Theme) -> None:
    """按 GUI 启动链的关键步骤配置应用实例。"""
    font = QFont("Microsoft YaHei")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    qconfig.set(qconfig.themeMode, theme)
    setTheme(theme)
    color = QColor("#2E75FF")
    qconfig.set(qconfig.themeColor, color)
    setThemeColor(color)


def _attach_preview_loader(window: MainWindow, tmp_path: Path) -> None:
    """给 OverviewPage 注入稳定的预览数据来源。"""
    preview_path = tmp_path / "hashes" / "16.5" / "champions" / "1.msgpack"
    loader = Mock()
    loader.load_mapping_preview.return_value = (
        preview_path,
        {
            "skins": {
                "4000": {
                    "events": {
                        "TwistedFate_Base_SFX": {
                            "Play_sfx_TwistedFate_Test": [1, 2],
                        }
                    }
                }
            }
        },
        "{\n  \"metadata\": \"window-preview\"\n}",
    )
    loader.load_available_audio_ids.return_value = {"1"}
    window.overviewInterface._loader = loader


def _seed_entity_rows(window: MainWindow) -> None:
    """向主窗口业务页注入最小实体列表样例数据。"""
    champion_rows = [
        {"id": "1", "name": "Annie", "alias": "annie", "audio": "已存在", "mapping": "未存在"},
        {"id": "103", "name": "Ahri", "alias": "ahri", "audio": "已存在", "mapping": "已存在"},
        {"id": "222", "name": "Jinx", "alias": "jinx", "audio": "未存在", "mapping": "未存在"},
    ]
    map_rows = [
        {"id": "11", "name": "Summoner's Rift", "alias": "sr", "audio": "已存在", "mapping": "已存在"},
    ]
    window.overviewInterface.set_entity_data("champions", champion_rows)
    window.overviewInterface.set_entity_data("maps", map_rows)
    window.executionInterface.set_entity_data("champions", champion_rows)
    window.executionInterface.set_entity_data("maps", map_rows)


def _dispose_main_window(window: MainWindow, app: QApplication) -> None:
    """以可预测的顺序关闭主窗口，避免遗留 QApplication 级状态。"""
    window.close()
    app.processEvents()


def test_main_window_home_primary_action_switches_to_execution_page(qtbot, monkeypatch) -> None:
    """首页主动作应切换到执行中心，而不是直接启动任务。"""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    qtbot.addWidget(window)
    switched_to: list[object] = []

    def _capture_switch(widget) -> None:
        switched_to.append(widget)

    monkeypatch.setattr(window, "switchTo", _capture_switch)

    qtbot.mouseClick(window.homeInterface.execution_center_card.action_button, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert switched_to == [window.executionInterface]
    _dispose_main_window(window, app)


def test_main_window_shows_before_bootstrap_and_finishes_splash(monkeypatch) -> None:
    """主窗口应先显示宿主，再继续启动链并结束启动页。"""
    app = QApplication.instance() or QApplication([])
    call_order: list[str] = []

    monkeypatch.setattr(MainWindow, "show", lambda self: call_order.append("show"))
    monkeypatch.setattr(
        MainWindow,
        "_bootstrap_after_show",
        lambda self, startup_begin, previous_mark: call_order.append("bootstrap") or previous_mark,
        raising=False,
    )
    monkeypatch.setattr(
        window_module.SplashScreen,
        "finish",
        lambda self: call_order.append("finish"),
    )

    window = MainWindow()
    app.processEvents()

    assert call_order == ["show", "bootstrap", "finish"]

    _dispose_main_window(window, app)


def test_main_window_does_not_initialize_dev_console_until_triggered(monkeypatch) -> None:
    """主窗口启动时不应立即创建开发控制台，但应保留调试命令入口。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    app.processEvents()

    assert getattr(window, "_dev_console", None) is None
    assert not hasattr(window, "_inject_mock_data")
    assert hasattr(window.executionInterface, "_debug_fill_mock_queue")
    assert hasattr(window.executionInterface, "_debug_clear_mock_queue")
    assert hasattr(window.executionInterface, "_debug_inspect_queue")

    _dispose_main_window(window, app)


def test_main_window_disables_refresh_action_while_task_queue_busy(monkeypatch) -> None:
    """任务执行期间应同时锁定设置页与手动刷新入口。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    app.processEvents()

    refresh_widget = window.navigationInterface.widget("refreshSharedData")
    assert refresh_widget is not None
    assert refresh_widget.isEnabled() is True

    window._on_task_queue_busy_changed(True)
    app.processEvents()

    assert window.settingInterface._runtime_config_locked is True
    assert refresh_widget.isEnabled() is False

    window._on_task_queue_busy_changed(False)
    app.processEvents()

    assert window.settingInterface._runtime_config_locked is False
    assert refresh_widget.isEnabled() is True

    _dispose_main_window(window, app)


def test_main_window_uses_real_app_icon_for_window_and_splash(monkeypatch) -> None:
    """主窗口与启动页都应使用当前资源目录中的应用图标。"""
    app = QApplication.instance() or QApplication([])
    captured: dict[str, object] = {}

    class FakeSplashScreen:
        """捕获启动页传入的图标，避免依赖真实闪屏绘制。"""

        def __init__(self, icon, parent) -> None:
            captured["icon"] = icon
            captured["parent"] = parent

        def setIconSize(self, _size) -> None:
            return None

        def raise_(self) -> None:
            return None

        def finish(self) -> None:
            return None

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    monkeypatch.setattr(window_module, "SplashScreen", FakeSplashScreen)

    window = MainWindow()
    app.processEvents()

    assert window.windowIcon().isNull() is False
    assert captured["icon"].isNull() is False
    assert captured["icon"].cacheKey() == window.windowIcon().cacheKey()
    assert captured["parent"] is window

    _dispose_main_window(window, app)


def test_main_window_overview_preview_tree_can_expand_with_custom_preview_tree(
    qtbot, monkeypatch, tmp_path
) -> None:
    """真实主窗口宿主里，自定义试听树也应正常展开并加载子节点。"""
    app = QApplication.instance() or QApplication([])
    original_theme = qconfig.theme
    original_color = qconfig.get(qconfig.themeColor)

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    qtbot.addWidget(window)

    try:
        _configure_gui_app(app, theme=Theme.DARK)
        _seed_entity_rows(window)
        _attach_preview_loader(window, tmp_path)
        window.switchTo(window.overviewInterface)
        window.overviewInterface._on_preview_mode_changed("audio")
        window.resize(1280, 860)
        window.show()
        app.processEvents()

        index = window.overviewInterface._entity_lists["champions"].model().index(0, 0)
        window.overviewInterface._load_preview_for_item("champions", index)
        app.processEvents()

        tree = window.overviewInterface.audio_preview_tree
        model = tree.model()
        assert isinstance(model, PreviewTreeModel)
        assert tree.styleSheet() != ""

        root_index = model.index(0, 0)
        tree.expand(root_index)
        app.processEvents()

        assert model.rowCount(root_index) == 1
    finally:
        setTheme(original_theme)
        setThemeColor(original_color)
        app.processEvents()
        _dispose_main_window(window, app)


def test_main_window_only_locks_runtime_config_while_queue_not_empty(monkeypatch, tmp_path) -> None:
    """队列未清空时仅锁定运行时配置，个性化设置仍应保持可编辑。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    monkeypatch.setattr(window.executionInterface, "_start_task_worker", lambda task: None)
    app.processEvents()

    game_root = tmp_path / "game-client"
    game_root.mkdir(parents=True, exist_ok=True)
    window.settingInterface.config.game_path = str(game_root)

    page = window.executionInterface
    page._queue_task_draft()
    page._queue_task_draft()
    app.processEvents()

    settings = window.settingInterface
    assert settings.isEnabled() is True
    assert settings.gamePathCard.isEnabled() is False
    assert settings.outputPathCard.isEnabled() is False
    assert settings.wwiserCard.isEnabled() is False
    assert settings.vgmstreamCard.isEnabled() is True
    assert settings.themeCard.isEnabled() is True
    assert settings.logDrawerAutoCollapseCard.isEnabled() is True

    first_item = page.draft_list.item(0)
    second_item = page.draft_list.item(1)
    first_payload = first_item.data(execution_page_module.TASK_ITEM_ROLE)
    second_payload = second_item.data(execution_page_module.TASK_ITEM_ROLE)
    result = ExecutionTaskResult(
        completed_steps=("音频解包",),
        summary="已完成：音频解包（0.8s）",
        duration_seconds=0.8,
    )

    page._on_task_finished(first_payload.task_id, result)
    app.processEvents()

    assert settings.gamePathCard.isEnabled() is False
    assert settings.themeCard.isEnabled() is True
    assert "[运行中]" in second_item.text()

    page._on_task_finished(second_payload.task_id, result)
    app.processEvents()

    assert settings.gamePathCard.isEnabled() is True
    assert settings.outputPathCard.isEnabled() is True
    assert settings.wwiserCard.isEnabled() is True
    assert settings.vgmstreamCard.isEnabled() is True
    assert settings.themeCard.isEnabled() is True
    assert settings.logDrawerAutoCollapseCard.isEnabled() is True

    _dispose_main_window(window, app)


def test_main_window_unregisters_global_event_filter_before_delete(monkeypatch) -> None:
    """主窗口销毁前应从 QApplication 移除全局 event filter。"""
    app = QApplication.instance() or QApplication([])
    removed_filters: list[object] = []

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    monkeypatch.setattr(
        QApplication,
        "removeEventFilter",
        lambda self, obj: removed_filters.append(obj),
        raising=False,
    )

    window = MainWindow()
    app.processEvents()
    _dispose_main_window(window, app)

    assert removed_filters
    assert removed_filters[0] is window


def test_main_window_auto_prepares_shared_data_after_missing_data_error(monkeypatch) -> None:
    """共享数据因缺少核心数据文件失败时，应自动转入后台数据准备。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    prepare_calls: list[object] = []

    def capture_prepare_request(cfg) -> None:
        prepare_calls.append(cfg)

    monkeypatch.setattr(
        window,
        "_start_shared_data_prepare",
        capture_prepare_request,
        raising=False,
    )
    window._allow_auto_prepare_on_shared_reload = True
    window._shared_data_auto_prepare_attempted = False
    app.processEvents()

    window._on_data_load_error("核心数据文件 (data.yml/json/msgpack) 不存在，请先运行更新程序。")
    app.processEvents()

    assert prepare_calls == [window.settingInterface.config]

    _dispose_main_window(window, app)


def test_prepare_shared_entity_data_does_not_inject_terminal_progress_flag(monkeypatch) -> None:
    """GUI 共享数据准备不应再写入终端进度相关遗留标志。"""
    fake_context = Mock(runtime_cache={})
    update_targets: list[str] = []
    create_overrides: list[dict[str, object]] = []

    class FakeApp:
        def __init__(self, ctx):
            self.ctx = ctx

        def update(self, _opts, *, target):
            update_targets.append(target)

    def fake_create_app_context(*, cli_overrides):
        create_overrides.append(dict(cli_overrides))
        return fake_context

    monkeypatch.setattr(window_module, "create_app_context", fake_create_app_context)
    monkeypatch.setattr(window_module, "LolAudioUnpackApp", FakeApp)

    window_module._prepare_shared_entity_data({"OUTPUT_PATH": r".\temp"})

    assert fake_context.runtime_cache == {}
    assert update_targets == ["all"]
    assert create_overrides == [{"OUTPUT_PATH": r".\temp", "WITH_BP_VO": True}]


def test_main_window_startup_auto_prepares_shared_data_when_manifest_is_missing(monkeypatch) -> None:
    """程序启动阶段若共享数据缺失，应直接转入后台数据准备。"""
    app = QApplication.instance() or QApplication([])
    prepare_calls: list[object] = []

    monkeypatch.setattr(window_module, "get_app_context_block_reason", lambda _cfg: None)
    monkeypatch.setattr(window_module, "create_app_context", lambda **_kwargs: Mock())
    monkeypatch.setattr(
        window_module.DataLoadWorker,
        "start",
        lambda self: self.error.emit("核心数据文件 (data.yml/json/msgpack) 不存在，请先运行更新程序。"),
    )
    monkeypatch.setattr(
        MainWindow,
        "_start_shared_data_prepare",
        lambda self, cfg: prepare_calls.append(cfg),
        raising=False,
    )

    window = MainWindow()
    app.processEvents()

    assert prepare_calls == [window.settingInterface.config]

    _dispose_main_window(window, app)


def test_main_window_output_path_change_keeps_reader_cache_without_auto_prepare(monkeypatch) -> None:
    """仅更改输出目录时，应复用现有 reader 缓存且不自动补 update。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    captured_reload_flags: list[tuple[bool, bool]] = []
    reset_calls: list[bool] = []

    monkeypatch.setattr(
        window,
        "_request_shared_data_reload",
        lambda *, show_notice, allow_auto_prepare: captured_reload_flags.append((show_notice, allow_auto_prepare)),
        raising=False,
    )
    monkeypatch.setattr(window_module, "_reset_data_reader_singleton", lambda: reset_calls.append(True))
    app.processEvents()

    cfg = window.settingInterface.config
    cfg.output_path = r".\new-output"
    window._on_shared_context_input_changed()
    app.processEvents()
    window._flush_pending_runtime_entity_refresh()
    app.processEvents()

    assert captured_reload_flags == [(False, False)]
    assert reset_calls == []

    _dispose_main_window(window, app)


def test_main_window_game_path_change_resets_reader_and_allows_auto_prepare(monkeypatch) -> None:
    """更改游戏目录时，应重置 reader 缓存并允许自动补 update。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    captured_reload_flags: list[tuple[bool, bool]] = []
    reset_calls: list[bool] = []

    monkeypatch.setattr(
        window,
        "_request_shared_data_reload",
        lambda *, show_notice, allow_auto_prepare: captured_reload_flags.append((show_notice, allow_auto_prepare)),
        raising=False,
    )
    monkeypatch.setattr(window_module, "_reset_data_reader_singleton", lambda: reset_calls.append(True))
    app.processEvents()

    cfg = window.settingInterface.config
    cfg.game_path = r".\another-game"
    window._on_shared_context_input_changed()
    app.processEvents()
    window._flush_pending_runtime_entity_refresh()
    app.processEvents()

    assert captured_reload_flags == [(False, True)]
    assert reset_calls == [True]

    _dispose_main_window(window, app)


def test_main_window_manual_refresh_falls_back_to_full_reload_without_shared_context(monkeypatch) -> None:
    """共享上下文未就绪时，手动刷新应回退到完整共享刷新。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    reload_calls: list[tuple[bool, bool]] = []
    reset_calls: list[bool] = []

    monkeypatch.setattr(
        window,
        "_request_shared_data_reload",
        lambda *, show_notice, allow_auto_prepare: reload_calls.append((show_notice, allow_auto_prepare)),
        raising=False,
    )
    monkeypatch.setattr(window_module, "_reset_data_reader_singleton", lambda: reset_calls.append(True))
    app.processEvents()

    window.settingInterface.config.output_path = r".\manual-refresh-output"
    window._refresh_shared_output_state()
    app.processEvents()

    assert reload_calls == [(True, True)]
    assert reset_calls == []

    _dispose_main_window(window, app)


def test_main_window_manual_refresh_logs_fallback_reason(monkeypatch) -> None:
    """共享上下文未就绪时，手动刷新应输出明确的回退日志。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    info_messages: list[str] = []

    def capture_info(message: str) -> None:
        info_messages.append(message)

    monkeypatch.setattr(window, "_request_shared_data_reload", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(window_module, "_reset_data_reader_singleton", lambda: None)
    monkeypatch.setattr(logger, "info", capture_info)
    app.processEvents()

    window._refresh_shared_output_state()
    app.processEvents()

    assert info_messages == ["共享上下文尚未就绪，回退到完整共享数据刷新"]

    _dispose_main_window(window, app)


def test_main_window_window_material_success_logs_trace_once_per_state(monkeypatch) -> None:
    """重复应用相同 Mica 状态时，不应重复输出成功日志。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    monkeypatch.setattr(window_module.sys, "platform", "win32")
    window = MainWindow()
    trace_messages: list[str] = []

    def capture_trace(message: str) -> None:
        trace_messages.append(message)

    try:
        monkeypatch.setattr(window, "isVisible", lambda: True, raising=False)
        monkeypatch.setattr(window.windowEffect, "setMicaEffect", lambda *args, **kwargs: None, raising=False)
        monkeypatch.setattr(window_module.logger, "trace", capture_trace, raising=False)
        window._last_window_material_logged_state = None
        app.processEvents()

        window._try_enable_window_material()
        window._try_enable_window_material()
        app.processEvents()

        assert trace_messages == ["主窗口已应用 Mica Alt 材质效果"]
    finally:
        _dispose_main_window(window, app)


def test_main_window_output_path_change_reconfigures_logging(monkeypatch) -> None:
    """更改输出目录时，应立即将日志目标切换到新的输出目录。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    reconfigure_calls: list[object] = []

    def capture_reconfigure_request(cfg) -> None:
        reconfigure_calls.append(cfg)

    monkeypatch.setattr(window, "_reconfigure_runtime_logging", capture_reconfigure_request, raising=False)
    app.processEvents()

    window.settingInterface.config.output_path = r".\reconfigured-output"
    window._on_shared_context_input_changed()
    app.processEvents()

    assert reconfigure_calls == [window.settingInterface.config]

    _dispose_main_window(window, app)


def test_main_window_champions_loaded_logs_info_with_clear_wording(monkeypatch) -> None:
    """英雄列表刷新完成后，应输出清晰的 info 级摘要日志。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    info_messages: list[str] = []

    def capture_info(message: str) -> None:
        info_messages.append(message)

    monkeypatch.setattr(window_module.DataLoadWorker, "start", lambda self: None)
    monkeypatch.setattr(logger, "info", capture_info)
    window._data_app_context = Mock()
    app.processEvents()

    window._on_champions_loaded([{"id": "1"}, {"id": "2"}])
    app.processEvents()

    assert "champions 实体列表已刷新，当前展示 2 项" in info_messages

    _dispose_main_window(window, app)


def test_gui_main_uses_info_console_log_level(monkeypatch, tmp_path: Path) -> None:
    """GUI 入口默认应以 INFO 作为控制台和窗口日志级别。"""
    setup_calls: list[dict[str, object]] = []
    expected_log_dir = tmp_path / "runtime-output" / "logs"

    class FakeApp:
        def __init__(self, _argv):
            pass

        @staticmethod
        def setHighDpiScaleFactorRoundingPolicy(_policy) -> None:
            return None

        @staticmethod
        def setAttribute(_attr) -> None:
            return None

        def setFont(self, _font) -> None:
            return None

        def exec(self) -> int:
            return 0

    class FakeConfig:
        theme_mode = "Light"
        theme_color = "#2E75FF"
        console_log_level = "INFO"
        file_log_level = "DEBUG"
        output_path = ""

        def load(self) -> None:
            return None

        def resolve_log_dir(self) -> Path:
            return expected_log_dir

    class FakeWindow:
        def isVisible(self) -> bool:
            return True

    monkeypatch.setattr(gui_main_module, "setup_logging", lambda **kwargs: setup_calls.append(kwargs))
    monkeypatch.setattr(gui_main_module, "install_startup_log_buffer", lambda: None)
    monkeypatch.setattr(gui_main_module, "remove_startup_log_buffer", lambda: None)
    monkeypatch.setattr(gui_main_module.logger, "enable", lambda _name: None)
    monkeypatch.setattr(gui_main_module.logger, "info", lambda _message: None)
    monkeypatch.setattr(gui_main_module, "QApplication", FakeApp)
    monkeypatch.setattr(gui_main_module, "GuiConfig", FakeConfig)
    monkeypatch.setattr(gui_main_module, "MainWindow", FakeWindow)
    monkeypatch.setattr(gui_main_module, "setTheme", lambda _theme: None)
    monkeypatch.setattr(gui_main_module, "setThemeColor", lambda _color: None)
    monkeypatch.setattr(gui_main_module.qconfig, "set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui_main_module.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    try:
        gui_main_module.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert setup_calls
    assert setup_calls[0]["log_level"] == "INFO"
    assert setup_calls[0]["file_log_level"] == "DEBUG"
    assert setup_calls[0]["log_file_path"] == expected_log_dir


def test_main_window_reconfigure_runtime_logging_uses_configured_levels(monkeypatch) -> None:
    """运行时日志重挂应使用设置页中的控制台和文件级别。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    setup_calls: list[dict[str, object]] = []
    sink_levels: list[str] = []

    monkeypatch.setattr(window_module, "setup_logging", lambda **kwargs: setup_calls.append(kwargs))
    monkeypatch.setattr(window.executionInterface, "attach_runtime_log_sink", lambda level="INFO": sink_levels.append(level))
    app.processEvents()

    window.settingInterface.config.console_log_level = "DEBUG"
    window.settingInterface.config.file_log_level = "TRACE"
    window._reconfigure_runtime_logging(window.settingInterface.config)
    app.processEvents()

    assert setup_calls
    assert setup_calls[-1]["log_level"] == "DEBUG"
    assert setup_calls[-1]["file_log_level"] == "TRACE"
    assert sink_levels[-1] == "DEBUG"

    _dispose_main_window(window, app)


def test_main_window_reconfigure_runtime_logging_uses_resolved_log_dir(monkeypatch, tmp_path: Path) -> None:
    """运行时日志重挂应使用解析后的有效日志目录，而不是原始 cwd 或空值。"""
    app = QApplication.instance() or QApplication([])
    expected_log_dir = tmp_path / "resolved-output" / "logs"

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    setup_calls: list[dict[str, object]] = []

    monkeypatch.setattr(window_module, "setup_logging", lambda **kwargs: setup_calls.append(kwargs))
    monkeypatch.setattr(window.executionInterface, "attach_runtime_log_sink", lambda level="INFO": None)
    monkeypatch.setattr(
        window.settingInterface.config,
        "resolve_log_dir",
        lambda: expected_log_dir,
        raising=False,
    )
    window.settingInterface.config.output_path = ""
    app.processEvents()

    window._reconfigure_runtime_logging(window.settingInterface.config)
    app.processEvents()

    assert setup_calls
    assert setup_calls[-1]["log_file_path"] == expected_log_dir

    _dispose_main_window(window, app)


def test_main_window_prepare_failure_does_not_restart_pending_refresh(monkeypatch) -> None:
    """共享数据准备失败后，不应立刻再次触发下一轮实体扫描。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    flush_calls: list[bool] = []

    monkeypatch.setattr(
        window,
        "_flush_pending_runtime_entity_refresh",
        lambda: flush_calls.append(True),
        raising=False,
    )
    app.processEvents()

    window._on_shared_data_prepare_failed("更新失败")
    app.processEvents()

    assert flush_calls == []

    _dispose_main_window(window, app)
