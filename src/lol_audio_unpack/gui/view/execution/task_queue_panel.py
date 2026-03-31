"""执行中心的任务队列列表面板。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMenu, QVBoxLayout, QWidget
from qfluentwidgets import ListWidget

from lol_audio_unpack.gui.task_models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    QueuedExecutionTask,
)

if TYPE_CHECKING:
    from lol_audio_unpack.gui.controllers.execution_queue_controller import ExecutionQueueController

QUEUE_VISIBLE_ROW_COUNT = 3
DEFAULT_QUEUE_PLACEHOLDER_TEXT = "当前任务队列为空。"
TASK_ITEM_ROLE = int(Qt.ItemDataRole.UserRole)


@dataclass(frozen=True, slots=True)
class TaskQueueContextMenuState:
    """任务队列右键菜单状态。"""

    remove_text: str | None
    remove_enabled: bool
    show_clear: bool
    clear_text: str | None


def build_task_queue_item_text(*, task_id: int, status: str, summary: str) -> str:
    """构造任务队列项文本。"""
    return f"#{task_id} · [{status}] {summary}"


def build_task_queue_context_menu_state(
    *,
    payload: QueuedExecutionTask | None,
    has_real_tasks: bool,
    has_running_task: bool,
    has_removable_tasks: bool,
) -> TaskQueueContextMenuState | None:
    """根据当前队列状态构造右键菜单展示状态。"""
    if payload is None and not has_real_tasks:
        return None

    remove_text: str | None = None
    remove_enabled = False
    if payload is not None:
        if payload.status == TASK_STATUS_RUNNING:
            remove_text = "运行中的任务暂不支持移除"
        else:
            remove_text = "删除该任务"
            remove_enabled = True

    clear_text: str | None = None
    if has_real_tasks and has_removable_tasks:
        clear_text = "清空全部非运行中任务" if has_running_task else "清空全部队列"

    return TaskQueueContextMenuState(
        remove_text=remove_text,
        remove_enabled=remove_enabled,
        show_clear=clear_text is not None,
        clear_text=clear_text,
    )


class TaskQueuePanel(QWidget):
    """承载执行中心队列列表。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """初始化任务队列列表区域。

        Args:
            parent: 父级控件。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.draft_list = ListWidget(self)
        self.draft_list.setAlternatingRowColors(True)
        layout.addWidget(self.draft_list)

    def _fallback_row_height(self) -> int:
        """返回用于列表高度估算的回退行高。"""
        return max(self.draft_list.fontMetrics().height() + 14, 32)

    def has_placeholder(self) -> bool:
        """返回当前列表是否仅显示占位文案。"""
        return self.draft_list.count() == 1 and self.draft_list.item(0).flags() == Qt.NoItemFlags

    def task_count(self) -> int:
        """返回当前真实任务项数量。"""
        if self.has_placeholder():
            return 0
        return self.draft_list.count()

    def task_items(self) -> tuple[QListWidgetItem, ...]:
        """返回当前所有真实任务项。"""
        items: list[QListWidgetItem] = []
        for index in range(self.draft_list.count()):
            item = self.draft_list.item(index)
            if item is None or item.flags() == Qt.NoItemFlags:
                continue
            items.append(item)
        return tuple(items)

    def status_counts(self) -> dict[str, int]:
        """统计当前队列中各任务状态的数量。"""
        counts = {
            TASK_STATUS_RUNNING: 0,
            TASK_STATUS_WAITING: 0,
            TASK_STATUS_COMPLETED: 0,
            TASK_STATUS_FAILED: 0,
            TASK_STATUS_CANCELLED: 0,
        }
        for item in self.task_items():
            payload = item.data(TASK_ITEM_ROLE)
            if not isinstance(payload, QueuedExecutionTask):
                continue
            if payload.status in counts:
                counts[payload.status] += 1
        return counts

    def find_task_item_by_id(self, task_id: int) -> QListWidgetItem | None:
        """按任务编号查找对应的列表项。"""
        for item in self.task_items():
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.task_id == task_id:
                return item
        return None

    def find_running_task_item(self) -> QListWidgetItem | None:
        """返回当前处于运行态的任务项。"""
        for item in self.task_items():
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.status == TASK_STATUS_RUNNING:
                return item
        return None

    def append_task(self, payload: QueuedExecutionTask, *, tooltip: str) -> QListWidgetItem:
        """向队列中追加一个真实任务项。"""
        if self.has_placeholder():
            self.draft_list.clear()
        item = QListWidgetItem(
            build_task_queue_item_text(
                task_id=payload.task_id,
                status=payload.status,
                summary=payload.summary,
            )
        )
        item.setData(TASK_ITEM_ROLE, payload)
        item.setToolTip(tooltip)
        self.draft_list.addItem(item)
        self.apply_list_height()
        return item

    def update_task(self, item: QListWidgetItem, payload: QueuedExecutionTask, *, tooltip: str) -> None:
        """把最新任务快照写回到既有列表项。"""
        item.setData(TASK_ITEM_ROLE, payload)
        item.setText(
            build_task_queue_item_text(
                task_id=payload.task_id,
                status=payload.status,
                summary=payload.summary,
            )
        )
        item.setToolTip(tooltip)

    def remove_task(self, item: QListWidgetItem) -> bool:
        """从列表中移除一个真实任务项。"""
        row = self.draft_list.row(item)
        if row < 0:
            return False
        self.draft_list.takeItem(row)
        if self.task_count() == 0:
            self.set_placeholder()
        else:
            self.apply_list_height()
        return True

    def clear_tasks(self) -> None:
        """清空当前所有列表项。"""
        self.draft_list.clear()

    def clear_non_running_tasks(self) -> int:
        """清空所有非运行中的任务项。"""
        removed_count = 0
        for index in range(self.draft_list.count() - 1, -1, -1):
            item = self.draft_list.item(index)
            payload = item.data(TASK_ITEM_ROLE)
            if isinstance(payload, QueuedExecutionTask) and payload.status != TASK_STATUS_RUNNING:
                self.draft_list.takeItem(index)
                removed_count += 1

        if removed_count > 0:
            if self.task_count() == 0:
                self.set_placeholder()
            else:
                self.apply_list_height()
        return removed_count

    def set_placeholder(self, text: str = DEFAULT_QUEUE_PLACEHOLDER_TEXT) -> None:
        """设置空队列占位文案。

        Args:
            text: 占位文案。
        """
        self.draft_list.clear()
        placeholder_item = QListWidgetItem(text)
        placeholder_item.setFlags(Qt.NoItemFlags)
        self.draft_list.addItem(placeholder_item)
        self.apply_list_height()

    def apply_list_height(self) -> None:
        """按默认可见行数同步队列列表高度。
        """
        row_height = self.draft_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = self._fallback_row_height()
        frame_height = self.draft_list.frameWidth() * 2
        self.draft_list.setFixedHeight(row_height * QUEUE_VISIBLE_ROW_COUNT + frame_height + 2)

    def open_context_menu(self, pos, *, queue_controller: ExecutionQueueController) -> None:
        """打开任务队列右键菜单。"""
        item = self.draft_list.itemAt(pos)
        has_real_tasks = self.task_count() > 0
        if item is not None and item.flags() == Qt.NoItemFlags:
            item = None
        if item is None and not has_real_tasks:
            return

        payload = item.data(TASK_ITEM_ROLE) if item is not None else None
        if item is not None and not isinstance(payload, QueuedExecutionTask):
            return

        counts = self.status_counts()
        has_removable_tasks = (
            counts[TASK_STATUS_WAITING]
            + counts[TASK_STATUS_COMPLETED]
            + counts[TASK_STATUS_FAILED]
            + counts[TASK_STATUS_CANCELLED]
        ) > 0
        state = build_task_queue_context_menu_state(
            payload=payload if isinstance(payload, QueuedExecutionTask) else None,
            has_real_tasks=has_real_tasks,
            has_running_task=self.find_running_task_item() is not None,
            has_removable_tasks=has_removable_tasks,
        )
        if state is None:
            return

        menu = QMenu(self.draft_list)
        remove_action = None
        if state.remove_text is not None:
            remove_action = menu.addAction(state.remove_text)
            remove_action.setEnabled(state.remove_enabled)

        clear_action = None
        if state.show_clear and state.clear_text is not None:
            if remove_action is not None:
                menu.addSeparator()
            clear_action = menu.addAction(state.clear_text)

        selected_action = menu.exec(self.draft_list.viewport().mapToGlobal(pos))
        if selected_action == remove_action and item is not None and state.remove_enabled:
            queue_controller.remove_task_item(item)
        if selected_action == clear_action:
            queue_controller.clear_draft_queue()
