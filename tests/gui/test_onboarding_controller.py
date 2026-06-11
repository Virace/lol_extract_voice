"""GUI 新手引导控制器测试。"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtWidgets import QWidget

from lol_audio_unpack.gui.controllers import onboarding as onboarding_module
from lol_audio_unpack.gui.controllers.onboarding import OnboardingMask, OnboardingTourController
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
        sourceModeCard=None if missing_first else _widget(qtbot),
        gamePathCard=_widget(qtbot),
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


def test_start_if_needed_ignores_completed_state(qtbot, monkeypatch) -> None:
    """当前引导版本已处理时不应创建气泡。"""

    controller, _config, window, created, _pages = _build_controller(
        qtbot,
        monkeypatch,
        should_show=False,
    )

    controller.start_if_needed()

    assert created == []
    assert window.switched == []


def test_start_if_needed_ignores_active_background_work(qtbot, monkeypatch) -> None:
    """存在后台任务时不应自动弹出引导。"""

    controller, _config, window, created, _pages = _build_controller(qtbot, monkeypatch, active=True)

    controller.start_if_needed()

    assert created == []
    assert window.switched == []


def test_start_anchors_to_settings_navigation_without_switching_page(qtbot, monkeypatch) -> None:
    """首次启动时应先提示设置入口，而不是直接跳转到设置页。"""

    controller, _config, window, created, _pages = _build_controller(qtbot, monkeypatch)

    controller.start()

    assert window.switched == []
    assert created[0]["target"] is window.settingNav
    assert created[0]["duration"] == -1


def test_switching_to_settings_advances_from_navigation_step(qtbot, monkeypatch) -> None:
    """用户点击设置入口后，引导应进入设置页内部步骤。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    first_tip = created[0]["tip"]

    window.stackedWidget.setCurrentWidget(pages.setting)

    assert first_tip.closed is True
    assert created[1]["target"] is pages.setting.sourceModeCard


def test_route_change_waits_before_showing_page_step(qtbot, monkeypatch) -> None:
    """路由变化后应等待页面动画结束再计算目标位置。"""

    callbacks: list[tuple[int, object]] = []
    created: list[dict[str, object]] = []

    def _make_tip(**kwargs):
        kwargs["tip"] = _FakeTip()
        created.append(kwargs)
        return kwargs["tip"]

    monkeypatch.setattr(onboarding_module.QTimer, "singleShot", lambda delay, callback: callbacks.append((delay, callback)))
    monkeypatch.setattr(onboarding_module.TeachingTip, "make", _make_tip)
    window = _FakeWindow()
    qtbot.addWidget(window)
    window.show()
    setting_page = _page(
        qtbot,
        "SettingPage",
        sourceModeCard=_widget(qtbot),
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
    assert created[-1]["target"] is setting_page.sourceModeCard


def test_next_closes_previous_tip_and_opens_next(qtbot, monkeypatch) -> None:
    """进入下一步时应关闭旧气泡并创建新气泡。"""

    controller, _config, _window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    first_tip = created[0]["tip"]

    controller._next()

    assert first_tip.closed is True
    assert created[1]["target"] is pages.setting.sourceModeCard


def test_next_from_settings_prompts_execution_navigation(qtbot, monkeypatch) -> None:
    """设置页讲完后应提示用户自己点击执行中心。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    created.clear()
    window.switched.clear()

    controller._next()
    controller._next()
    controller._next()

    assert window.switched == []
    assert created[-1]["target"] is window.executionNav


def test_switching_to_execution_advances_from_navigation_step(qtbot, monkeypatch) -> None:
    """用户点击执行中心后，引导应进入执行中心内部步骤。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    controller._next()
    controller._next()
    controller._next()
    execution_tip = created[-1]["tip"]

    window.stackedWidget.setCurrentWidget(pages.execution)

    assert execution_tip.closed is True
    assert created[-1]["target"] is pages.execution.taskBuilderPanel


def test_next_from_execution_prompts_overview_navigation(qtbot, monkeypatch) -> None:
    """执行中心讲完后应提示用户自己点击实体总览。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.execution)
    created.clear()
    window.switched.clear()

    controller._next()
    controller._next()
    controller._next()
    controller._next()

    assert window.switched == []
    assert created[-1]["target"] is window.overviewNav


def test_next_from_overview_prompts_item_lookup_navigation(qtbot, monkeypatch) -> None:
    """实体总览讲完后应提示用户自己点击装备查询。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.execution)
    controller._next()
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.overview)
    created.clear()
    window.switched.clear()

    controller._next()
    controller._next()

    assert window.switched == []
    assert created[-1]["target"] is window.itemLookupNav


def test_switching_to_item_lookup_advances_from_navigation_step(qtbot, monkeypatch) -> None:
    """用户点击装备查询后，引导应进入装备查询页内部步骤。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.execution)
    controller._next()
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.overview)
    controller._next()
    controller._next()
    item_lookup_tip = created[-1]["tip"]

    window.stackedWidget.setCurrentWidget(pages.item_lookup)

    assert item_lookup_tip.closed is True
    assert created[-1]["target"] is pages.item_lookup.search_input


def test_next_from_item_lookup_explains_mode_tabs(qtbot, monkeypatch) -> None:
    """装备查询页搜索框之后应继续说明模式 tab 与复制 ID。"""

    controller, _config, window, created, pages = _build_controller(qtbot, monkeypatch)
    controller.start()
    window.stackedWidget.setCurrentWidget(pages.setting)
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.execution)
    controller._next()
    controller._next()
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.overview)
    controller._next()
    controller._next()
    window.stackedWidget.setCurrentWidget(pages.item_lookup)
    created.clear()

    controller._next()

    assert created[-1]["target"] is pages.item_lookup.mode_tabs
    assert "复制 ID" in created[-1]["view"].contentLabel.text()


def test_skip_marks_state_and_closes_tip(qtbot, monkeypatch) -> None:
    """跳过引导时应持久化跳过状态并关闭气泡。"""

    controller, config, _window, created, _pages = _build_controller(qtbot, monkeypatch)
    controller.start()

    controller._skip()

    assert config.skipped == [GUIDE_VERSION]
    assert created[0]["tip"].closed is True


def test_finish_marks_state_and_closes_tip(qtbot, monkeypatch) -> None:
    """完成引导时应持久化完成状态并关闭气泡。"""

    controller, config, _window, created, _pages = _build_controller(qtbot, monkeypatch)
    controller.start()

    controller._finish()

    assert config.completed == [GUIDE_VERSION]
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

    assert created[-1]["target"] is pages.setting.gamePathCard


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
        sourceModeCard=_widget(qtbot),
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


def test_onboarding_mask_covers_outside_target_and_leaves_target_hole(qtbot) -> None:
    """蒙版应覆盖非目标区域，并在目标控件周围留出透明点击区域。"""

    host = QWidget()
    host.resize(300, 200)
    target = QWidget(host)
    target.setGeometry(80, 60, 80, 40)
    qtbot.addWidget(host)
    host.show()
    target.show()

    mask = OnboardingMask(host)
    mask.set_target(target)
    mask.show()

    assert mask.mask().contains(QPoint(10, 10)) is True
    assert mask.mask().contains(QPoint(120, 80)) is False


def test_onboarding_mask_uses_rounded_target_hole(qtbot) -> None:
    """透明区域应使用圆角，避免目标高亮边缘显得生硬。"""

    host = QWidget()
    host.resize(300, 200)
    target = QWidget(host)
    target.setGeometry(80, 60, 80, 40)
    qtbot.addWidget(host)
    host.show()
    target.show()

    mask = OnboardingMask(host, padding=0, radius=16)
    mask.set_target(target)
    mask.show()

    assert mask.mask().contains(QPoint(82, 62)) is True
    assert mask.mask().contains(QPoint(120, 80)) is False
