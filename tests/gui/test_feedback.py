"""测试全局通知时长策略。"""

from __future__ import annotations

from qfluentwidgets import InfoBarPosition

import lol_audio_unpack.gui.common.feedback as feedback_module


def test_calculate_feedback_duration_keeps_error_visible_until_manual_close() -> None:
    """error 级全局通知应保持常驻，等待用户手动关闭。"""
    assert feedback_module.calculate_feedback_duration(
        title="刷新失败",
        content="共享实体数据准备失败。",
        level="error",
    ) == -1


def test_show_feedback_infobar_uses_persistent_duration_for_error(monkeypatch) -> None:
    """error 级通知应以常驻模式显示。"""
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        feedback_module.InfoBar,
        "error",
        staticmethod(lambda **kwargs: calls.append(kwargs)),
    )

    feedback_module.show_feedback_infobar(
        parent=object(),
        title="任务执行失败",
        content="请检查输出目录。",
        level="error",
        position=InfoBarPosition.TOP,
    )

    assert calls
    assert calls[0]["duration"] == -1
