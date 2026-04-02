"""执行中心任务创建摘要测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.view.execution import task_builder_panel


def test_build_task_scope_summary_includes_preflight_forced_update() -> None:
    assert (
        task_builder_panel._build_task_scope_summary(
            include_preflight_update=True,
            include_extract=True,
            include_mapping=False,
        )
        == "前置强制更新 + 音频解包"
    )


def test_build_task_scope_summary_handles_empty_steps() -> None:
    assert (
        task_builder_panel._build_task_scope_summary(
            include_preflight_update=False,
            include_extract=False,
            include_mapping=False,
        )
        == "未选择执行内容"
    )


def test_build_task_scope_summary_does_not_treat_preflight_update_as_standalone_task() -> None:
    assert (
        task_builder_panel._build_task_scope_summary(
            include_preflight_update=True,
            include_extract=False,
            include_mapping=False,
        )
        == "未选择执行内容"
    )
