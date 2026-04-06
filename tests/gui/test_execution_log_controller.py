from __future__ import annotations

from lol_audio_unpack.gui.controllers.execution_log import ExecutionLogController


def test_execution_log_controller_flushes_pending_lines_into_current_text() -> None:
    controller = ExecutionLogController(
        initial_lines=("boot",),
        max_lines=10,
        log_format="{message}",
    )

    controller.queue_runtime_log_line("line-1")
    controller.queue_runtime_log_line("line-2")

    assert controller.current_log_text() == "boot\nline-1\nline-2"


def test_execution_log_controller_emits_appended_lines_once_per_flush() -> None:
    controller = ExecutionLogController(
        initial_lines=(),
        max_lines=10,
        log_format="{message}",
    )
    appended_batches: list[tuple[str, ...]] = []
    controller.log_lines_appended.connect(lambda lines: appended_batches.append(tuple(lines)))

    controller.queue_runtime_log_line("alpha")
    controller.queue_runtime_log_line("beta")
    controller.flush_pending_log_lines()

    assert appended_batches == [("alpha", "beta")]
