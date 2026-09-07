"""GUI 新手引导控制器测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from lol_audio_unpack.gui.controllers import onboarding as onboarding_module
from lol_audio_unpack.gui.controllers.onboarding import OnboardingTourController
from lol_audio_unpack.gui.controllers.onboarding_state import GUIDE_VERSION

MIN_ROUTE_SETTLE_DELAY_MS = 300


class _FakeConfig:
    """记录新手引导状态调用的配置替身。"""

    def __init__(self, *, should_show: bool = True) -> None:
        self.should_show = should_show
        self.completed: list[str] = []
        self.skipped: list[str] = []

    def should_show_onboarding(self, guide_version: str) -> bool:
        return self.should_show and guide_version == GUIDE_VERSION

    def mark_onboarding_completed(self, guide_version: str) -> None:
        self.completed.append(guide_version)

    def mark_onboarding_skipped(self, guide_version: str) -> None:
        self.skipped.append(guide_version)


class _FakeWindow(QWidget):
    """记录页面切换调用的窗口替身。"""

    def __init__(self) -> None:
        super().__init__()
        self.resize(420, 320)
        self.switched: list[object] = []
        self.settingNav = QWidget(self)
        self.settingNav.setGeometry(12, 250, 120, 42)
        self.executionNav = QWidget(self)
        self.executionNav.setGeometry(12, 92, 120, 42)
        self.overviewNav = QWidget(self)
        self.overviewNav.setGeometry(12, 140, 120, 42)
        self.itemLookupNav = QWidget(self)
        self.itemLookupNav.setGeometry(12, 188, 120, 42)
        self.settingNav.show()
        self.executionNav.show()
        self.overviewNav.show()
        self.itemLookupNav.show()
        self.navigationInterface = SimpleNamespace(widget=self._navigation_widget)
        self.stackedWidget = _FakeStack()

    def switchTo(self, page) -> None:
        self.switched.append(page)
        if isinstance(page, QWidget):
            page.show()
        self.stackedWidget.setCurrentWidget(page)

    def _navigation_widget(self, route_key: str) -> QWidget:
        items = {
            "SettingPage": self.settingNav,
            "ExecutionPage": self.executionNav,
            "OverviewPage": self.overviewNav,
            "ItemLookupPage": self.itemLookupNav,
        }
        if route_key not in items:
            raise KeyError(route_key)
        return items[route_key]


class _FakeStack(QObject):
    """提供当前页变更信号的 stackedWidget 替身。"""

    currentChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._current = None

    def currentWidget(self):
        return self._current

    def setCurrentWidget(self, widget) -> None:
        self._current = widget
        self.currentChanged.emit(0)


class _FakeTip:
    """记录关闭状态的 TeachingTip 替身。"""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _widget(qtbot, parent: QWidget | None = None) -> QWidget:
    widget = QWidget(parent)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def _page(qtbot, name: str, **targets: QWidget | None) -> SimpleNamespace:
    page = SimpleNamespace(**targets)
    page.ensureWidgetVisible = lambda _target: None
    page.objectName = lambda: name
    for target in targets.values():
        if target is not None:
            target.show()
    return page


def _build_controller(qtbot, monkeypatch, *, should_show: bool = True, active: bool = False, missing_first=False):
    created: list[dict[str, object]] = []

    def _make_tip(**kwargs):
        tip = _FakeTip()
        kwargs["tip"] = tip
        created.append(kwargs)
        return tip

    monkeypatch.setattr(onboarding_module.QTimer, "singleShot", lambda _delay, callback: callback())
    monkeypatch.setattr(onboarding_module.TeachingTip, "make", _make_tip)

    window = _FakeWindow()
    qtbot.addWidget(window)
    window.show()
    setting_page = _page(
        qtbot,
        "SettingPage",
        gamePathCard=None if missing_first else _widget(qtbot),
        outputPathCard=_widget(qtbot),
        wwiserCard=_widget(qtbot),
    )
    execution_page = _page(
        qtbot,
        "ExecutionPage",
        taskBuilderPanel=_widget(qtbot),
        vo_filter=_widget(qtbot),
        wav_task_cb=_widget(qtbot),
        mapping_task_cb=_widget(qtbot),
    )
    overview_page = _page(
        qtbot,
        "OverviewPage",
        entityListPanel=_widget(qtbot),
        previewPanel=_widget(qtbot),
        audio_preview_tree=_widget(qtbot),
    )
    item_lookup_page = _page(
        qtbot,
        "ItemLookupPage",
        search_input=_widget(qtbot),
        mode_tabs=_widget(qtbot),
    )
    config = _FakeConfig(should_show=should_show)
    controller = OnboardingTourController(
        window=window,
        config=config,
        setting_page=setting_page,
        execution_page=execution_page,
        overview_page=overview_page,
        item_lookup_page=item_lookup_page,
        has_active_work=lambda: active,
    )
    pages = SimpleNamespace(
        setting=setting_page,
        execution=execution_page,
        overview=overview_page,
        item_lookup=item_lookup_page,
    )
    return controller, config, window, created, pages


@pytest.mark.parametrize(
    ("should_show", "active"),
    [
        (False, False),
        (True, True),
    ],
)
def test_start_if_needed_respects_persisted_and_runtime_gates(
    qtbot,
    monkeypatch,
    should_show: bool,
    active: bool,
) -> None:
    """已处理引导或存在后台任务时都不应自动启动。"""
    controller, _config, window, created, _pages = _build_controller(
        qtbot,
        monkeypatch,
        should_show=should_show,
        active=active,
    )

    controller.start_if_needed()

    assert created == []
    assert window.switched == []


def test_onboarding_walks_complete_navigation_and_page_flow(qtbot, monkeypatch) -> None:
    """完整引导应按导航入口和页内控件顺序推进并最终持久化完成态。"""
    controller, config, window, created, pages = _build_controller(qtbot, monkeypatch)

    controller.start()
    assert window.switched == []
    assert created[-1]["target"] is window.settingNav
    assert created[-1]["duration"] == -1

    previous_tip = created[-1]["tip"]
    window.stackedWidget.setCurrentWidget(pages.setting)
    assert previous_tip.closed is True
    assert created[-1]["target"] is pages.setting.gamePathCard

    for target in (pages.setting.outputPathCard, window.executionNav):
        previous_tip = created[-1]["tip"]
        controller._next()
        assert previous_tip.closed is True
        assert created[-1]["target"] is target

    window.stackedWidget.setCurrentWidget(pages.execution)
    assert created[-1]["target"] is pages.execution.taskBuilderPanel
    for target in (
        pages.execution.vo_filter,
        pages.execution.wav_task_cb,
        pages.execution.mapping_task_cb,
        window.overviewNav,
    ):
        controller._next()
        assert created[-1]["target"] is target

    window.stackedWidget.setCurrentWidget(pages.overview)
    assert created[-1]["target"] is pages.overview.entityListPanel
    for target in (pages.overview.previewPanel, window.itemLookupNav):
        controller._next()
        assert created[-1]["target"] is target

    window.stackedWidget.setCurrentWidget(pages.item_lookup)
    assert created[-1]["target"] is pages.item_lookup.search_input
    controller._next()
    assert created[-1]["target"] is pages.item_lookup.mode_tabs
    controller._next()
    assert created[-1]["target"] is window.settingNav

    window.stackedWidget.setCurrentWidget(pages.setting)
    assert created[-1]["target"] is pages.setting.wwiserCard
    final_tip = created[-1]["tip"]
    controller._next()

    assert config.completed == [GUIDE_VERSION]
    assert final_tip.closed is True


def test_route_change_waits_before_showing_page_step(qtbot, monkeypatch) -> None:
    """路由变化后应等待页面动画结束再计算目标位置。"""

    callbacks: list[tuple[int, object]] = []
    created: list[dict[str, object]] = []

    def _make_tip(**kwargs):
        kwargs["tip"] = _FakeTip()
        created.append(kwargs)
        return kwargs["tip"]

    monkeypatch.setattr(
        onboarding_module.QTimer, "singleShot", lambda delay, callback: callbacks.append((delay, callback))
    )
    monkeypatch.setattr(onboarding_module.TeachingTip, "make", _make_tip)
    window = _FakeWindow()
    qtbot.addWidget(window)
    window.show()
    setting_page = _page(
        qtbot,
        "SettingPage",
        gamePathCard=_widget(qtbot),
        outputPathCard=_widget(qtbot),
        wwiserCard=_widget(qtbot),
    )
    controller = OnboardingTourController(
        window=window,
        config=_FakeConfig(),
        setting_page=setting_page,
        execution_page=_page(qtbot, "ExecutionPage"),
        overview_page=_page(qtbot, "OverviewPage"),
        item_lookup_page=_page(qtbot, "ItemLookupPage"),
        has_active_work=lambda: False,
    )

    controller.start()
    callbacks.pop(0)[1]()
    window.stackedWidget.setCurrentWidget(setting_page)

    assert callbacks[-1][0] >= MIN_ROUTE_SETTLE_DELAY_MS
    callbacks.pop()[1]()
    assert created[-1]["target"] is setting_page.gamePathCard


@pytest.mark.parametrize(
    ("action_name", "state_name"),
    [
        ("_skip", "skipped"),
        ("_finish", "completed"),
    ],
)
def test_terminal_actions_persist_state_and_close_tip(
    qtbot,
    monkeypatch,
    action_name: str,
    state_name: str,
) -> None:
    """跳过或完成都应持久化对应状态并关闭当前气泡。"""
    controller, config, _window, created, _pages = _build_controller(qtbot, monkeypatch)
    controller.start()

    getattr(controller, action_name)()

    assert getattr(config, state_name) == [GUIDE_VERSION]
    assert created[0]["tip"].closed is True


def test_missing_target_skips_to_next_available_step(qtbot, monkeypatch) -> None:
    """目标控件缺失时应跳到下一个可用步骤。"""

    controller, _config, _window, created, pages = _build_controller(
        qtbot,
        monkeypatch,
        missing_first=True,
    )

    controller.start()

    controller._next()

    assert created[-1]["target"] is pages.setting.outputPathCard


def test_close_before_delayed_show_prevents_tip_creation(qtbot, monkeypatch) -> None:
    """关闭控制器后，尚未执行的延迟回调不应再创建气泡。"""

    callbacks = []
    created: list[dict[str, object]] = []

    def _make_tip(**kwargs):
        kwargs["tip"] = _FakeTip()
        created.append(kwargs)
        return kwargs["tip"]

    monkeypatch.setattr(onboarding_module.QTimer, "singleShot", lambda _delay, callback: callbacks.append(callback))
    monkeypatch.setattr(onboarding_module.TeachingTip, "make", _make_tip)

    window = _FakeWindow()
    qtbot.addWidget(window)
    setting_page = _page(
        qtbot,
        "SettingPage",
        gamePathCard=_widget(qtbot),
        outputPathCard=_widget(qtbot),
        wwiserCard=_widget(qtbot),
    )
    execution_page = _page(qtbot, "ExecutionPage")
    overview_page = _page(qtbot, "OverviewPage")
    controller = OnboardingTourController(
        window=window,
        config=_FakeConfig(),
        setting_page=setting_page,
        execution_page=execution_page,
        overview_page=overview_page,
        item_lookup_page=_page(qtbot, "ItemLookupPage"),
        has_active_work=lambda: False,
    )

    controller.start()
    controller.close()
    callbacks[0]()

    assert created == []
