"""共享数据类型化展示映射测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.shared_data import (
    SharedDataPhase,
    SharedDataProblem,
    SharedDataProblemCode,
    SharedDataProgress,
    SharedDataState,
    SharedDataSummary,
)
from lol_audio_unpack.gui.shared_data_view import describe_shared_data_state


def test_shared_data_display_uses_real_progress_counts() -> None:
    """可测量阶段必须保留 current/total，未知阶段不能伪造百分比。"""
    unknown = describe_shared_data_state(SharedDataState(SharedDataPhase.CHECKING, 3))
    known = describe_shared_data_state(
        SharedDataState(
            SharedDataPhase.VERIFYING,
            3,
            progress=SharedDataProgress(3, "maps", "advanced", current=4, total=9),
        )
    )

    assert unknown.has_determinate_progress is False
    assert unknown.progress_current is None
    assert known.has_determinate_progress is True
    assert known.progress_text == "地图数据 · 4/9"
    assert (known.progress_current, known.progress_total) == (4, 9)


def test_shared_data_display_normalizes_out_of_range_progress() -> None:
    """异常 current 不得让计数文案或进度条越过真实 total。"""
    display = describe_shared_data_state(
        SharedDataState(
            SharedDataPhase.PREPARING,
            3,
            progress=SharedDataProgress(3, "champion_banks", "advanced", current=200, total=173),
        )
    )

    assert display.progress_text == "英雄数据 · 173/173"
    assert (display.progress_current, display.progress_total) == (173, 173)


def test_shared_data_display_ready_and_partial_share_authoritative_summary() -> None:
    """就绪与部分可用文案必须来自同一份动态扫描摘要。"""
    summary = SharedDataSummary(173, 172, 1, 9, 9, 0, 63, 0, 63)
    ready = describe_shared_data_state(SharedDataState(SharedDataPhase.READY, 4, summary=summary))
    partial = describe_shared_data_state(SharedDataState(SharedDataPhase.PARTIAL, 4, summary=summary))

    assert ready.detail_text == "已加载 172 个英雄和 9 张地图。"
    assert ready.task_block_reason == ""
    assert partial.detail_text == "英雄 172/173，地图 9/9；新任务已暂停。"
    assert partial.task_block_reason == partial.detail_text


def test_shared_data_display_escalates_persisting_schema_problem_to_regenerate() -> None:
    """普通修复后仍存在同类 schema 问题时才提供显式强制重建。"""
    problem = SharedDataProblem(
        SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH,
        "champions",
        "英雄资源仍为旧 schema。",
        ("1",),
    )
    initial = describe_shared_data_state(SharedDataState(SharedDataPhase.PARTIAL, 5, problem=problem))
    retried = describe_shared_data_state(
        SharedDataState(
            SharedDataPhase.PARTIAL,
            5,
            problem=problem,
            prepare_attempted=True,
        )
    )

    assert (initial.action_key, initial.action_text) == ("retry", "重试更新")
    assert (retried.action_key, retried.action_text) == (
        "regenerate",
        "重新生成实体数据",
    )
