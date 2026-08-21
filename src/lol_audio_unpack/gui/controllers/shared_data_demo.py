"""生成只作用于 GUI 展示层的共享数据进度样本。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from lol_audio_unpack.gui.shared_data import (
    SharedDataPhase,
    SharedDataProgress,
    SharedDataState,
    SharedDataSummary,
)
from lol_audio_unpack.model.progress import OperationProgress, ProgressEvent

DEMO_CHAMPION_TOTAL = 173
DEMO_MAP_TOTAL = 9
DEMO_CHECKING_TICKS = 20
DEMO_READY_TICKS = 20


def _progress_event(current: int, total: int) -> ProgressEvent:
    """按当前位置返回与真实进度合同一致的生命周期事件。"""
    if current == 0:
        return "started"
    if current == total:
        return "finished"
    return "advanced"


def build_shared_data_demo_states(
    *,
    generation: int,
    source_mode: str,
    champion_total: int = DEMO_CHAMPION_TOTAL,
    map_total: int = DEMO_MAP_TOTAL,
) -> tuple[SharedDataState, ...]:
    """构造一次完整检查、更新、复检与就绪的 mock 状态序列。

    Args:
        generation: 供展示协调器识别的状态代次。
        source_mode: 当前 GUI 配置的数据来源模式。
        champion_total: 模拟的英雄总量。
        map_total: 模拟的地图总量。

    Returns:
        可由真实页面组件直接消费的不可变状态序列。

    Raises:
        ValueError: 任一实体总量不是正整数时抛出。
    """
    if champion_total <= 0 or map_total <= 0:
        raise ValueError("mock 实体总量必须为正整数")

    checking = SharedDataState(SharedDataPhase.CHECKING, generation, source_mode)
    states = [checking] * DEMO_CHECKING_TICKS

    for stage_key, total, entity_type in (
        ("champion_banks", champion_total, "champions"),
        ("map_banks", map_total, "maps"),
    ):
        for current in range(total + 1):
            states.append(
                SharedDataState(
                    SharedDataPhase.PREPARING,
                    generation,
                    source_mode,
                    progress=OperationProgress(
                        operation_key="update",
                        stage_key=stage_key,
                        event=_progress_event(current, total),
                        current=current,
                        total=total,
                        entity_type=entity_type,
                    ),
                )
            )

    for stage_key, total in (("champions", champion_total), ("maps", map_total)):
        for current in range(total + 1):
            states.append(
                SharedDataState(
                    SharedDataPhase.VERIFYING,
                    generation,
                    source_mode,
                    progress=SharedDataProgress(
                        generation=generation,
                        stage_key=stage_key,
                        event=_progress_event(current, total),
                        current=current,
                        total=total,
                    ),
                )
            )

    ready = SharedDataState(
        SharedDataPhase.READY,
        generation,
        source_mode,
        summary=SharedDataSummary(
            champion_expected=champion_total,
            champion_loaded=champion_total,
            champion_failed=0,
            map_expected=map_total,
            map_loaded=map_total,
            map_failed=0,
            special_discovered=0,
            special_prepared=0,
            special_unprepared=0,
        ),
    )
    states.extend([ready] * DEMO_READY_TICKS)
    return tuple(states)


class SharedDataProgressDemo(QObject):
    """按固定间隔循环发布共享数据 mock 状态。"""

    state_changed = Signal(object)

    def __init__(self, *, interval_ms: int, parent: QObject | None = None) -> None:
        """初始化循环进度发布器。

        Args:
            interval_ms: 每个状态样本之间的毫秒间隔。
            parent: Qt 对象父级。

        Raises:
            ValueError: 刷新间隔不是正整数时抛出。
        """
        if interval_ms <= 0:
            raise ValueError("mock 进度间隔必须为正整数")
        super().__init__(parent)
        self._states: tuple[SharedDataState, ...] = ()
        self._next_index = 0
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._publish_next)

    def start(self, *, generation: int, source_mode: str) -> None:
        """从检查阶段开始循环发布一轮完整状态。

        Args:
            generation: 供展示协调器识别的状态代次。
            source_mode: 当前 GUI 配置的数据来源模式。
        """
        self._states = build_shared_data_demo_states(generation=generation, source_mode=source_mode)
        self._next_index = 0
        self._publish_next()
        self._timer.start()

    def stop(self) -> None:
        """停止发布 mock 状态。"""
        self._timer.stop()

    def _publish_next(self) -> None:
        """发布下一个样本，并在抵达末尾时回到检查阶段。"""
        if not self._states:
            return
        state = self._states[self._next_index]
        self._next_index = (self._next_index + 1) % len(self._states)
        self.state_changed.emit(state)


__all__ = [
    "SharedDataProgressDemo",
    "build_shared_data_demo_states",
]
