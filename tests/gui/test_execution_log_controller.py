"""验证执行日志控制器的批量刷新状态。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers import execution_log as execution_log_module
from lol_audio_unpack.gui.controllers.execution_log import ExecutionLogController


def test_execution_log_controller_flushes_each_batch_once() -> None:
    """待处理日志应合入当前文本，并且每批只发出一次追加信号。"""
    controller = ExecutionLogController(
        initial_lines=("boot",),
        max_lines=10,
        log_format="{message}",
    )
    appended_batches: list[tuple[str, ...]] = []
    controller.log_lines_appended.connect(lambda lines: appended_batches.append(tuple(lines)))

    controller.queue_runtime_log_line("alpha")
    controller.queue_runtime_log_line("beta")
    controller.flush_pending_log_lines()
    controller.flush_pending_log_lines()

    assert controller.current_log_text() == "boot\nalpha\nbeta"
    assert appended_batches == [("alpha", "beta")]


def test_execution_log_controller_attaches_non_blocking_sink(monkeypatch) -> None:
    """运行时日志 sink 必须异步入队，并可按返回标识准确卸载。"""
    sink_calls: list[tuple[object, dict[str, object]]] = []
    removed_sink_ids: list[int] = []
    sink_id = 17
    monkeypatch.setattr(execution_log_module.logger, "enable", lambda _name: None)
    monkeypatch.setattr(
        execution_log_module.logger,
        "add",
        lambda sink, **options: sink_calls.append((sink, options)) or sink_id,
    )
    monkeypatch.setattr(execution_log_module.logger, "remove", removed_sink_ids.append)
    controller = ExecutionLogController(
        initial_lines=(),
        max_lines=10,
        log_format="{message}",
    )

    controller.attach_runtime_log_sink("debug")

    assert len(sink_calls) == 1
    _sink, options = sink_calls[0]
    assert options == {
        "level": "DEBUG",
        "colorize": False,
        "enqueue": True,
        "format": "{message}",
    }

    controller.detach_runtime_log_sink()

    assert removed_sink_ids == [sink_id]
