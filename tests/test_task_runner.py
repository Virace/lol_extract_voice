"""执行中心运行时 settings 归一测试。"""

from __future__ import annotations

from pathlib import Path
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


def _build_task(
    *,
    source_mode: str,
    run_update: bool = False,
    run_mapping: bool = True,
    wav_enabled: bool = False,
) -> QueuedExecutionTask:
    return QueuedExecutionTask(
        task_id=1,
        summary="test",
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="manual",
            context_input=AppContextInputSnapshot(
                settings=(
                    ("SOURCE_MODE", source_mode),
                    ("GAME_PATH", "game"),
                    ("OUTPUT_PATH", "output"),
                    ("GAME_REGION", "zh_CN"),
                )
            ),
            task_params=ExecutionTaskParamsSnapshot(
                run_update=run_update,
                run_mapping=run_mapping,
                wav_enabled=wav_enabled,
            ),
        ),
    )


def test_build_runtime_settings_forces_local_path_when_packaged(monkeypatch) -> None:
    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_settings",
        lambda settings: {**settings, "SOURCE_MODE": "local_path"},
        raising=False,
    )

    settings = task_runner._build_runtime_settings(_build_task(source_mode="remote_snapshot"))

    assert settings["SOURCE_MODE"] == "local_path"


def test_prepare_shared_entity_data_normalizes_source_mode_before_app_context(monkeypatch) -> None:
    captured: dict[str, str | bool] = {}

    class _FakeApp:
        def __init__(self, _app_context) -> None:
            pass

        def update(self, _options, *, target: str) -> None:
            assert target == "all"

    def _fake_create_app_context(*, settings):
        captured.update(settings)
        return object()

    monkeypatch.setattr(
        window_module,
        "normalize_app_context_settings",
        lambda settings: {**settings, "SOURCE_MODE": "local_path"},
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

    def _fake_create_app_context(*, settings) -> object:
        _ = settings
        return object()

    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_settings",
        lambda settings: {**settings, "SOURCE_MODE": "local_path"},
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
    assert any("共享上下文快照" in message and "OUTPUT_PATH" in message for message in debugs)
    assert any("参数快照" in message and "run_mapping" in message for message in debugs)
    assert debugs.count("[执行中心] 任务 #1 创建运行时 AppContext") == 1
    assert successes == [f"[执行中心] 任务 #1 {result.summary}"]


def test_run_execution_task_logs_preflight_forced_update_step(monkeypatch) -> None:
    task = _build_task(source_mode="remote_snapshot", run_update=True)
    infos: list[str] = []
    debugs: list[str] = []
    successes: list[str] = []

    def _fail_exception(message: str) -> None:
        pytest.fail(message)

    def _fake_create_app_context(*, settings) -> object:
        _ = settings
        return object()

    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_settings",
        lambda settings: {**settings, "SOURCE_MODE": "local_path"},
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

        def update(self, _options, *, target: str) -> None:
            assert target == "all"

        def extract(self, _options, **kwargs) -> None:
            kwargs["progress_callback"]("champions", 1, 1, "音频解包完成")

        def mapping(self, _options, **_kwargs) -> None:
            return None

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert infos[0] == "[执行中心] 任务 #1 开始执行: 前置强制更新 -> 音频解包 -> 事件映射"
    assert infos[1] == "[执行中心] 任务 #1 开始前置强制更新"
    assert successes == [f"[执行中心] 任务 #1 {result.summary}"]


def test_run_execution_task_detaches_wav_process_from_mapping(monkeypatch, tmp_path: Path) -> None:
    task = _build_task(source_mode="remote_snapshot", wav_enabled=True)
    events: list[object] = []

    def _fail_exception(message: str) -> None:
        pytest.fail(message)

    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(),
    )

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = None

        def poll(self) -> int | None:
            return self.returncode

    fake_process = FakeProcess()

    monkeypatch.setattr(
        task_runner,
        "normalize_app_context_settings",
        lambda settings: {**settings, "SOURCE_MODE": "local_path"},
        raising=False,
    )
    monkeypatch.setattr(
        task_runner,
        "logger",
        SimpleNamespace(
            info=lambda _message: None,
            debug=lambda _message: None,
            success=lambda _message: None,
            exception=_fail_exception,
        ),
    )
    monkeypatch.setattr(task_runner, "create_app_context", lambda *, settings: runtime_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, options, **kwargs) -> None:
            assert options.wav_output.enabled is True
            assert kwargs["detach_wav"] is True
            events.append(("extract", kwargs["detach_wav"]))
            return fake_process

        def mapping(self, _options, **_kwargs) -> None:
            events.append("mapping")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == [("extract", True), "mapping"]
    assert result.wav_background_process is fake_process
    assert result.wav_background_notice == "任务 #1 的事件映射已完成，WAV 转码仍在后台继续。"
    assert "WAV 转码仍在后台继续" in result.summary
