"""GUI 新手引导控制器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QBitmap, QColor, QPainter, QPainterPath, QPaintEvent, QRegion
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, TeachingTip, TeachingTipTailPosition, TeachingTipView

from lol_audio_unpack.gui.controllers.onboarding_state import GUIDE_VERSION

_NORMAL_STEP_DELAY_MS = 120
_NAV_STEP_DELAY_MS = 80
_ROUTE_SETTLE_DELAY_MS = 420
_MASK_RESYNC_DELAYS_MS = (0, 120, 320)
_MASK_HOLE_RADIUS = 8


@dataclass(frozen=True, slots=True)
class TourStep:
    """单个新手引导步骤。"""

    key: str
    page_name: str
    target: Callable[[], QWidget | None]
    title: str
    content: str
    tail_position: TeachingTipTailPosition = TeachingTipTailPosition.BOTTOM
    allow_next: bool = True
    wait_for_page_name: str | None = None


class OnboardingMask(QWidget):
    """新手引导期间阻断非目标区域点击的蒙版。"""

    def __init__(self, host: QWidget, *, padding: int = 8, radius: int = _MASK_HOLE_RADIUS) -> None:
        """创建覆盖主窗口的引导蒙版。

        Args:
            host: 蒙版覆盖的宿主窗口。
            padding: 目标控件周围保留的透明边距。
            radius: 目标透明区域的圆角半径。
        """

        super().__init__(host)
        self._host = host
        self._target: QWidget | None = None
        self._padding = padding
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setGeometry(host.rect())
        host.installEventFilter(self)

    def set_target(self, target: QWidget) -> None:
        """设置当前高亮目标控件。"""

        self._target = target
        self.sync()

    def sync(self) -> None:
        """同步宿主窗口尺寸和透明目标区域。"""

        self.setGeometry(self._host.rect())
        hole = self._target_rect()
        self.setMask(self._mask_region(hole))
        self.update()

    def eventFilter(self, watched, event) -> bool:
        """宿主窗口变化时刷新蒙版区域。"""

        if watched is self._host and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.WindowStateChange,
        }:
            QTimer.singleShot(0, self.sync)
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:
        """关闭时解除宿主事件过滤。"""

        self._host.removeEventFilter(self)
        super().closeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制半透明遮罩。"""

        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 135))

    def _target_rect(self) -> QRect:
        """返回目标控件在宿主窗口坐标系中的透明区域。"""

        if self._target is None or not self._target.isVisible():
            return QRect()
        pos = self._target.mapTo(self._host, QPoint(0, 0))
        return QRect(pos, self._target.size()).adjusted(
            -self._padding,
            -self._padding,
            self._padding,
            self._padding,
        ).intersected(self.rect())

    def _mask_region(self, hole: QRect) -> QRegion:
        """返回扣除目标圆角透明区域后的蒙版命中区域。"""

        if hole.isNull():
            return QRegion(self.rect())

        bitmap = QBitmap(self.size())
        bitmap.fill(Qt.GlobalColor.color1)

        radius = min(self._radius, hole.width() // 2, hole.height() // 2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(hole), radius, radius)

        painter = QPainter(bitmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.color0)
        painter.drawPath(path)
        painter.end()

        return QRegion(bitmap)


class OnboardingTourController:
    """管理首次引导的步骤、跳转、气泡与持久化状态。"""

    def __init__(  # noqa: PLR0913
        self,
        *,
        window,
        config,
        setting_page,
        execution_page,
        overview_page,
        has_active_work: Callable[[], bool],
    ) -> None:
        """创建新手引导控制器。

        Args:
            window: 主窗口对象，需要提供 ``switchTo``。
            config: GUI 配置对象，需要提供引导状态方法。
            setting_page: 设置页实例。
            execution_page: 执行中心实例。
            overview_page: 实体总览实例。
            has_active_work: 判断是否存在后台任务的回调。
        """

        self._window = window
        self._config = config
        self._setting_page = setting_page
        self._execution_page = execution_page
        self._overview_page = overview_page
        self._has_active_work = has_active_work
        self._steps = self._build_steps()
        self._index = 0
        self._tip: QWidget | None = None
        self._mask: OnboardingMask | None = None
        self._running = False
        self._route_settle_pending = False
        current_changed = getattr(getattr(window, "stackedWidget", None), "currentChanged", None)
        if current_changed is not None:
            current_changed.connect(self._on_current_page_changed)

    def start_if_needed(self) -> None:
        """满足首次展示条件时启动引导。"""

        if not self._config.should_show_onboarding(GUIDE_VERSION):
            return
        if self._has_active_work():
            return
        self.start()

    def start(self) -> None:
        """从第一步开始展示引导。"""

        self._running = True
        self._index = 0
        self._show_current()

    def close(self) -> None:
        """关闭当前气泡并释放引用。"""

        self._running = False
        self._close_tip()
        self._close_mask()

    def _next(self) -> None:
        """进入下一步。"""

        if self._index >= len(self._steps) - 1:
            self._finish()
            return
        self._index += 1
        self._show_current()

    def _skip(self) -> None:
        """跳过当前引导版本。"""

        self._config.mark_onboarding_skipped(GUIDE_VERSION)
        self.close()

    def _finish(self) -> None:
        """完成当前引导版本。"""

        self._config.mark_onboarding_completed(GUIDE_VERSION)
        self.close()

    def _show_current(self) -> None:
        """切换页面并延迟展示当前步骤。"""

        self._close_tip()
        self._close_mask()
        if not self._running:
            return
        if self._index >= len(self._steps):
            return

        step = self._steps[self._index]
        self._switch_to_step_page(step)
        QTimer.singleShot(self._step_delay(step), lambda: self._show_step(step))

    def _show_step(self, step: TourStep) -> None:
        """展示指定步骤；目标不可用时跳过到下一步。"""

        if not self._running or self._index >= len(self._steps) or self._steps[self._index] is not step:
            return

        target = step.target()
        if target is None or not target.isVisible():
            self._index += 1
            self._show_current()
            return

        self._ensure_visible(step, target)
        self._show_mask(target)
        view = TeachingTipView(
            title=step.title,
            content=step.content,
            isClosable=False,
            tailPosition=step.tail_position,
        )
        view.addWidget(self._build_buttons())
        self._tip = TeachingTip.make(
            view=view,
            target=target,
            duration=-1,
            tailPosition=step.tail_position,
            parent=self._window,
            isDeleteOnClose=True,
        )
        if hasattr(self._tip, "raise_"):
            self._tip.raise_()

    def _build_buttons(self) -> QWidget:
        """构建当前步骤的操作按钮。"""

        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)

        skip_button = PushButton("跳过")
        skip_button.clicked.connect(self._skip)
        layout.addWidget(skip_button, 0, Qt.AlignmentFlag.AlignRight)

        step = self._steps[self._index]
        if step.allow_next:
            next_button = PrimaryPushButton("完成" if self._index >= len(self._steps) - 1 else "下一步")
            next_button.clicked.connect(self._finish if self._index >= len(self._steps) - 1 else self._next)
            layout.addWidget(next_button, 0, Qt.AlignmentFlag.AlignRight)
        return row

    def _switch_to_step_page(self, step: TourStep) -> None:
        """按步骤切换到对应页面。"""

        if step.page_name == "navigation":
            return
        page = self._page_for(step.page_name)
        if page is None or self._current_page() is page:
            return
        self._route_settle_pending = True
        self._window.switchTo(page)

    def _ensure_visible(self, step: TourStep, target: QWidget) -> None:
        """尽量滚动到目标控件位置。"""

        page = self._page_for(step.page_name)
        ensure = getattr(page, "ensureWidgetVisible", None)
        if callable(ensure):
            ensure(target)

    def _on_current_page_changed(self, _index: int) -> None:
        """用户切换到设置页后从导航入口步骤继续。"""

        if not self._running or self._index >= len(self._steps):
            return
        step = self._steps[self._index]
        if step.wait_for_page_name is None:
            return

        if self._current_page() is self._page_for(step.wait_for_page_name):
            self._route_settle_pending = True
            self._next()

    def _page_for(self, name: str) -> Any:
        """返回步骤名称对应的页面对象。"""

        return {
            "settings": self._setting_page,
            "execution": self._execution_page,
            "overview": self._overview_page,
        }.get(name)

    def _current_page(self) -> Any:
        """返回当前显示页面。"""

        current_widget = getattr(getattr(self._window, "stackedWidget", None), "currentWidget", None)
        return current_widget() if callable(current_widget) else None

    def _step_delay(self, step: TourStep) -> int:
        """返回展示当前步骤前应等待的时间。"""

        if step.page_name == "navigation":
            return _NAV_STEP_DELAY_MS
        if self._route_settle_pending:
            self._route_settle_pending = False
            return _ROUTE_SETTLE_DELAY_MS
        return _NORMAL_STEP_DELAY_MS

    def _close_tip(self) -> None:
        """关闭当前 TeachingTip。"""

        if self._tip is not None:
            self._tip.close()
            self._tip = None

    def _show_mask(self, target: QWidget) -> None:
        """展示蒙版并让当前目标区域可点击。"""

        self._close_mask()
        self._mask = OnboardingMask(self._window)
        self._mask.set_target(target)
        self._mask.show()
        self._mask.raise_()
        for delay in _MASK_RESYNC_DELAYS_MS:
            QTimer.singleShot(delay, self._sync_mask)

    def _sync_mask(self) -> None:
        """动画或布局变化后重算蒙版透明区域。"""

        if self._mask is not None:
            self._mask.sync()

    def _close_mask(self) -> None:
        """关闭当前蒙版。"""

        if self._mask is not None:
            self._mask.close()
            self._mask.deleteLater()
            self._mask = None

    def _target_nav_for(self, page_name: str) -> QWidget | None:
        """返回左侧导航中的页面入口。"""

        nav = getattr(self._window, "navigationInterface", None)
        if nav is None:
            return None
        page = self._page_for(page_name)
        route_key = page.objectName() if page is not None and callable(getattr(page, "objectName", None)) else ""
        if not route_key:
            route_key = {
                "settings": "SettingPage",
                "execution": "ExecutionPage",
                "overview": "OverviewPage",
            }.get(page_name, "")
        try:
            return nav.widget(route_key)
        except Exception:
            return None

    def _build_steps(self) -> tuple[TourStep, ...]:
        """构建第一版新手引导步骤。"""

        return (
            TourStep(
                key="settings-entry",
                page_name="navigation",
                target=lambda: self._target_nav_for("settings"),
                title="先打开全局设置",
                content="全局设置在左侧导航栏底部。请点击这个入口，进入设置页后我会继续说明游戏目录和输出目录。",
                allow_next=False,
                wait_for_page_name="settings",
            ),
            TourStep(
                key="source-mode",
                page_name="settings",
                target=lambda: getattr(self._setting_page, "sourceModeCard", None),
                title="来源模式",
                content="多数用户保持本地模式即可，它会读取你电脑里的英雄联盟客户端目录。远程模式适合没有完整游戏目录的情况，第一步不用改。",
            ),
            TourStep(
                key="game-path",
                page_name="settings",
                target=lambda: getattr(self._setting_page, "gamePathCard", None),
                title="游戏位置",
                content="这里选择英雄联盟安装相关位置，不需要精确理解根目录。可以选安装目录、Game 目录或 LeagueClient 目录，程序会自动识别真正的游戏目录。",
            ),
            TourStep(
                key="output-path",
                page_name="settings",
                target=lambda: getattr(self._setting_page, "outputPathCard", None),
                title="输出目录",
                content="输出目录保存导出的 .wem、可选 .wav、事件映射文件和报告。建议选一个容易找到的空文件夹，不要放进游戏安装目录。",
            ),
            TourStep(
                key="execution-entry",
                page_name="navigation",
                target=lambda: self._target_nav_for("execution"),
                title="打开执行中心",
                content="执行中心在左侧导航栏。请点击它，进入后我会说明怎样选择目标、音频范围和任务类型。",
                allow_next=False,
                wait_for_page_name="execution",
            ),
            TourStep(
                key="task-scope",
                page_name="execution",
                target=lambda: getattr(self._execution_page, "taskBuilderPanel", None),
                title="创建任务",
                content="执行中心决定这次要处理哪些英雄或地图，以及要做解包、转码还是事件映射。先选少量目标测试，再扩大范围更稳。",
            ),
            TourStep(
                key="audio-range",
                page_name="execution",
                target=lambda: getattr(self._execution_page, "vo_filter", None),
                title="音频范围",
                content="VO 是英雄语音，通常是台词和播报；SFX 是技能、环境等音效；MUSIC 是音乐。默认先处理 VO，适合大多数语音导出需求。",
            ),
            TourStep(
                key="wav-transcode",
                page_name="execution",
                target=lambda: getattr(self._execution_page, "wav_task_cb", None),
                title="音频转码",
                content="解包会得到原始 .wem。只有勾选音频转码后，格式选项才会启用，用来额外导出 wav 等更容易播放的文件。",
            ),
            TourStep(
                key="event-mapping",
                page_name="execution",
                target=lambda: getattr(self._execution_page, "mapping_task_cb", None),
                title="事件映射",
                content="事件映射用于把游戏事件名和音频文件关联起来。想查某句语音对应哪个事件时再勾选；只想导出音频可以不选。",
            ),
            TourStep(
                key="overview-entry",
                page_name="navigation",
                target=lambda: self._target_nav_for("overview"),
                title="打开实体总览",
                content="实体总览在左侧导航栏。请点击它，进入后我会说明如何查看英雄、地图和事件音频。",
                allow_next=False,
                wait_for_page_name="overview",
            ),
            TourStep(
                key="overview-list",
                page_name="overview",
                target=lambda: getattr(self._overview_page, "entityListPanel", None),
                title="实体总览",
                content="这里查看英雄和地图的数据状态，也可以把选中的实体发送到执行中心，避免手动输入编号或别名。",
            ),
            TourStep(
                key="overview-preview",
                page_name="overview",
                target=lambda: getattr(
                    self._overview_page,
                    "previewPanel",
                    getattr(self._overview_page, "audio_preview_tree", None),
                ),
                title="事件与音频预览",
                content="更新和映射完成后，可以在这里查看事件树、音频列表和试听结果。看不到内容时，通常需要先更新数据或执行映射。",
            ),
            TourStep(
                key="settings-tools-entry",
                page_name="navigation",
                target=lambda: self._target_nav_for("settings"),
                title="回到全局设置",
                content="最后回到全局设置，看一下高级工具路径。请点击左侧的全局设置入口。",
                allow_next=False,
                wait_for_page_name="settings",
            ),
            TourStep(
                key="advanced-tools",
                page_name="settings",
                target=lambda: getattr(self._setting_page, "wwiserCard", None),
                title="高级工具",
                content="wwiser 和 vgmstream-cli 现在不是普通流程必填项。默认会使用内置能力；遇到高级兼容需求时，再按文档设置这些路径。",
            ),
        )


__all__ = ["GUIDE_VERSION", "OnboardingMask", "OnboardingTourController", "TourStep"]
