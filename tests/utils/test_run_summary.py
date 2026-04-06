"""验证命令行执行总结的输出行为。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.utils.run_summary import CliRunSummary, emit_cli_run_summary


def test_emit_cli_run_summary_separates_clean_issue_and_explanatory_notes(tmp_path: Path) -> None:
    """验证执行总结会区分正常阶段、异常阶段和说明信息。"""
    summary = CliRunSummary()

    with summary.stage_context("update", label="数据更新"):
        summary.record_note("update", "地图 33 的事件因公共地图去重被省略。", detail="category=AMB_SFX, removed=3")

    with summary.stage_context("extract", label="音频解包"):
        pass

    with summary.stage_context("mapping", label="事件映射"):
        summary.record_log("ERROR", "构建地图映射失败: simulated error")

    info_messages: list[str] = []
    debug_messages: list[str] = []
    fake_logger = SimpleNamespace(info=info_messages.append, debug=debug_messages.append)

    emit_cli_run_summary(summary, log=fake_logger, log_path=tmp_path / "logs")

    assert info_messages[0] == "执行总结："
    assert any("无异常: 音频解包" in message for message in info_messages)
    assert any("需要关注: 事件映射 (错误 1 条)" in message for message in info_messages)
    assert any("可解释差异: 数据更新 -> 地图 33 的事件因公共地图去重被省略。" in message for message in info_messages)
    assert any("构建地图映射失败" in message for message in debug_messages)
    assert any("category=AMB_SFX" in message for message in debug_messages)


def test_emit_cli_run_summary_includes_extract_wav_breaker_note(tmp_path: Path) -> None:
    """验证 extraction 阶段的 WAV breaker 说明会出现在执行总结中。"""
    summary = CliRunSummary()

    with summary.stage_context("extract", label="音频解包"):
        summary.record_note(
            "extract",
            "已启用 WAV 转码，但因系统性失败自动降级为仅保留 WEM。",
            detail="breaker=recent_failures, failed=12, skipped=1772",
        )

    info_messages: list[str] = []
    debug_messages: list[str] = []
    fake_logger = SimpleNamespace(info=info_messages.append, debug=debug_messages.append)

    emit_cli_run_summary(summary, log=fake_logger, log_path=tmp_path / "logs")

    assert any(
        "可解释差异: 音频解包 -> 已启用 WAV 转码，但因系统性失败自动降级为仅保留 WEM。" in msg
        for msg in info_messages
    )
