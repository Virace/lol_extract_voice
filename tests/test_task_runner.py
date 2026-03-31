"""执行中心运行时 overrides 归一测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.gui.service import task_runner
from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.window import _prepare_shared_entity_data


def _build_task(*, source_mode: str) -> QueuedExecutionTask:
    return QueuedExecutionTask(
        task_id=1,
        summary="test",
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="manual",
            context_input=AppContextInputSnapshot(
                overrides=(
                    ("SOURCE_MODE", source_mode),
                    ("GAME_PATH", "game"),
                    ("OUTPUT_PATH", "output"),
                    ("GAME_REGION", "zh_CN"),
                )
            ),
            task_params=ExecutionTaskParamsSnapshot(),
        ),
    )


def test_build_runtime_overrides_forces_local_path_when_packaged(monkeypatch) -> None:
    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_overrides",
        lambda overrides: {**overrides, "SOURCE_MODE": "local_path"},
        raising=False,
    )

    overrides = task_runner._build_runtime_overrides(_build_task(source_mode="remote_snapshot"))

    assert overrides["SOURCE_MODE"] == "local_path"


def test_prepare_shared_entity_data_normalizes_source_mode_before_app_context(monkeypatch) -> None:
    captured: dict[str, str | bool] = {}

    class _FakeApp:
        def __init__(self, _app_context) -> None:
            pass

        def update(self, _options, *, target: str) -> None:
            assert target == "all"

    def _fake_create_app_context(*, cli_overrides):
        captured.update(cli_overrides)
        return object()

    monkeypatch.setattr(
        window_module,
        "normalize_app_context_overrides",
        lambda overrides: {**overrides, "SOURCE_MODE": "local_path"},
        raising=False,
    )
    monkeypatch.setattr(window_module, "create_app_context", _fake_create_app_context)
    monkeypatch.setattr(window_module, "LolAudioUnpackApp", _FakeApp)

    _prepare_shared_entity_data({"SOURCE_MODE": "remote_snapshot"})

    assert captured["SOURCE_MODE"] == "local_path"


def test_run_execution_task_logs_task_start_and_summary(monkeypatch) -> None:
    task = _build_task(source_mode="remote_snapshot")
    infos: list[str] = []
    debugs: list[str] = []
    successes: list[str] = []

    def _fail_exception(message: str) -> None:
        pytest.fail(message)

    def _fake_create_app_context(*, cli_overrides) -> object:
        _ = cli_overrides
        return object()

    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_overrides",
        lambda overrides: {**overrides, "SOURCE_MODE": "local_path"},
        raising=False,
    )
    monkeypatch.setattr(
        task_runner,
        "logger",
        SimpleNamespace(
            info=infos.append,
            debug=debugs.append,
            success=successes.append,
            exception=_fail_exception,
        ),
    )
    monkeypatch.setattr(task_runner, "create_app_context", _fake_create_app_context)

    class FakeApp:
        def __init__(self, _app_context) -> None:
            pass

        def extract(self, _options, **kwargs) -> None:
            kwargs["progress_callback"]("champions", 1, 1, "音频解包完成")

        def mapping(self, _options, **_kwargs) -> None:
            return None

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert infos[0] == "[执行中心] 任务 #1 开始执行: 音频解包 -> 事件映射"
    assert debugs[0] == "[执行中心] 任务 #1 范围=英雄 + 地图, source_mode=local_path"
    assert debugs.count("[执行中心] 任务 #1 创建运行时 AppContext") == 1
    assert successes == [f"[执行中心] 任务 #1 {result.summary}"]
