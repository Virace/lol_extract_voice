"""测试主窗口宿主中的基础预览树。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

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

    window.deleteLater()
    app.processEvents()


def test_main_window_does_not_initialize_dev_console_until_triggered(monkeypatch) -> None:
    """主窗口启动时不应立即创建开发控制台，但应保留调试命令入口。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    app.processEvents()

    assert getattr(window, "_dev_console", None) is None
    assert hasattr(window.executionInterface, "_debug_fill_mock_queue")
    assert hasattr(window.executionInterface, "_debug_clear_mock_queue")
    assert hasattr(window.executionInterface, "_debug_inspect_queue")

    window.deleteLater()
    app.processEvents()


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
        window._inject_mock_data()
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


def test_main_window_only_locks_runtime_config_while_queue_not_empty(monkeypatch) -> None:
    """队列未清空时仅锁定运行时配置，个性化设置仍应保持可编辑。"""
    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(MainWindow, "_load_initial_data", lambda self, cfg: None)
    window = MainWindow()
    monkeypatch.setattr(window.executionInterface, "_start_task_worker", lambda task: None)
    app.processEvents()

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

    window.deleteLater()
    app.processEvents()


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

    window.deleteLater()
    app.processEvents()
