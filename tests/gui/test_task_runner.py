"""执行中心运行时 settings 归一测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.gui.service import task_runner
from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    QueuedExecutionTask,
)
from lol_audio_unpack.gui.window import _prepare_shared_entity_data

EXPECTED_CONTEXT_COUNT_WITH_UPDATE = 2


def _build_task(  # noqa: PLR0913
    *,
    source_mode: str,
    run_update: bool = False,
    run_extract: bool = True,
    run_mapping: bool = True,
    wav_enabled: bool = False,
    champion_ids: tuple[int, ...] | None = None,
    special_targets: tuple[str, ...] = (),
    resource_pack_wads: tuple[ResourcePackWadRef, ...] = (),
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
                champion_ids=champion_ids,
                special_targets=special_targets,
                resource_pack_wads=resource_pack_wads,
                run_update=run_update,
                run_extract=run_extract,
                run_mapping=run_mapping,
                wav_enabled=wav_enabled,
            ),
        ),
    )


class _ReadyMapBanksReader:
    """提供已就绪地图 banks 的轻量测试读取器。"""

    def __init__(self, *, ctx) -> None:
        self.ctx = ctx

    def get_maps(self) -> list[dict]:
        return [{"id": 11}]

    def get_map_banks(self, _map_id: int) -> dict:
        return {"banks": {"VO": [["map.wpk"]]}}


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


def test_run_execution_task_runs_stages_in_order_and_reuses_runtime_context(monkeypatch, tmp_path: Path) -> None:
    """完整任务应隔离强制更新，并让后续阶段复用同一运行时上下文。"""
    task = _build_task(source_mode="remote_snapshot", run_update=True, wav_enabled=True)
    events: list[object] = []
    context_settings: list[dict[str, object]] = []

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

    def _create_app_context(*, settings):
        context_settings.append(settings)
        return runtime_context

    monkeypatch.setattr(task_runner, "create_app_context", _create_app_context)
    monkeypatch.setattr(task_runner, "DataReader", _ReadyMapBanksReader)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def update(self, _options, *, target: str) -> None:
            assert target == "all"
            events.append("update")

        def extract(self, options, **_kwargs) -> None:
            assert options.wav_output.enabled is True
            events.append("extract")

        def transcode_wav(self, options, **_kwargs) -> None:
            assert options.wav_output.enabled is True
            events.append("wav")

        def mapping(self, _options, **_kwargs) -> None:
            events.append("mapping")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    task_runner.run_execution_task(task, signals)

    assert events == ["update", "extract", "wav", "mapping"]
    assert len(context_settings) == EXPECTED_CONTEXT_COUNT_WITH_UPDATE
    assert all(settings["SOURCE_MODE"] == "local_path" for settings in context_settings)


def test_run_execution_task_allows_wav_stage_without_extract(monkeypatch, tmp_path: Path) -> None:
    task = _build_task(source_mode="remote_snapshot", run_extract=False, run_mapping=False, wav_enabled=True)
    events: list[str] = []

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

        def extract(self, _options, **_kwargs) -> None:
            pytest.fail("未勾选音频解包时不应执行 extract")

        def transcode_wav(self, options, **_kwargs) -> None:
            assert options.wav_output.enabled is True
            events.append("wav")

        def mapping(self, _options, **_kwargs) -> None:
            pytest.fail("未勾选事件映射时不应执行 mapping")

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    result = task_runner.run_execution_task(task, signals)

    assert events == ["wav"]
    assert result.completed_steps == ("音频转码",)


def test_run_execution_task_rejects_missing_map_banks_before_runtime_steps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """地图 banks 尚未生成时，GUI 任务不应静默跳过地图输出。"""
    task = _build_task(source_mode="local_path", run_mapping=False)
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(
            manifest_path=tmp_path / "manifest",
            audio_path=tmp_path / "audios",
            wav_path=tmp_path / "wavs",
            report_path=tmp_path / "reports",
        ),
        runtime_cache={},
        config=SimpleNamespace(dev_mode=False),
    )
    data_dir = runtime_context.paths.manifest_path / "16.5"
    data_dir.mkdir(parents=True)
    (data_dir / "data.msgpack").write_bytes(b"placeholder")

    class FakeReader:
        version = "16.5"

        def __init__(self, *, ctx) -> None:
            pass

        def get_champions(self) -> list[dict]:
            return [{"id": 1}]

        def get_maps(self) -> list[dict]:
            return [{"id": 11}]

        def get_map_banks(self, _map_id: int):
            return None

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, **_kwargs) -> None:
            pytest.fail("地图 banks 缺失时不应进入 extract")

    monkeypatch.setattr(task_runner, "create_app_context", lambda *, settings: runtime_context)
    monkeypatch.setattr(task_runner, "DataReader", FakeReader)
    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    with pytest.raises(RuntimeError, match="地图基础数据仍未准备完成"):
        task_runner.run_execution_task(task, signals)


def test_run_execution_task_rejects_remote_special_targets_before_app_context(monkeypatch) -> None:
    """远端 special key 必须在任何运行时上下文与 stage 前失败。"""
    task = _build_task(source_mode="remote_snapshot", special_targets=("champion:66600",))
    calls: list[str] = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    monkeypatch.setattr(
        task_runner,
        "create_app_context",
        lambda **_kwargs: calls.append("context") or pytest.fail("不应创建 AppContext"),
    )
    monkeypatch.setattr(
        task_runner,
        "LolAudioUnpackApp",
        lambda *_args: calls.append("app") or pytest.fail("不应创建运行 App"),
    )

    with pytest.raises(ValueError, match="特殊内容仅支持本地客户端资源"):
        task_runner.run_execution_task(task, signals)

    assert calls == []


def test_run_execution_task_preserves_special_targets_for_app_facade(monkeypatch, tmp_path: Path) -> None:
    """GUI runner 不得把异构 special key 错当作普通英雄 ID。"""
    task = _build_task(
        source_mode="local_path",
        run_mapping=False,
        champion_ids=(1, 66600),
        special_targets=("champion:66600", "champion:77702"),
    )
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(audio_path=tmp_path / "audios", wav_path=tmp_path / "wavs"),
        runtime_cache={},
        config=SimpleNamespace(),
    )
    captured = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    monkeypatch.setattr(task_runner, "create_app_context", lambda **_kwargs: runtime_context)

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, options, **_kwargs) -> None:
            captured.append(options)

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)

    task_runner.run_execution_task(task, signals)

    assert len(captured) == 1
    assert captured[0].champion_ids == (1, 66600)
    assert captured[0].special_targets == ("champion:66600", "champion:77702")


def test_resource_pack_only_task_excludes_champion_and_map_runtime_scope(monkeypatch, tmp_path: Path) -> None:
    """仅资源包任务不得退化为全量英雄/地图，也不能触发地图 banks 检查。"""
    key = build_resource_pack_key("Legacy.wad.client", "MODE_LEGACY")
    task = _build_task(source_mode="local_path", run_mapping=False, special_targets=(key,))
    runtime_context = SimpleNamespace(
        paths=SimpleNamespace(audio_path=tmp_path / "audios", wav_path=tmp_path / "wavs"),
        runtime_cache={},
        config=SimpleNamespace(),
    )
    calls: list[tuple[bool, bool]] = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))

    monkeypatch.setattr(task_runner, "create_app_context", lambda **_kwargs: runtime_context)
    monkeypatch.setattr(task_runner, "DataReader", lambda **_kwargs: pytest.fail("不应检查地图 banks"))

    class FakeApp:
        def __init__(self, app_context) -> None:
            self.ctx = app_context

        def extract(self, _options, *, include_champions: bool, include_maps: bool, **_kwargs) -> None:
            calls.append((include_champions, include_maps))

    monkeypatch.setattr(task_runner, "LolAudioUnpackApp", FakeApp)

    task_runner.run_execution_task(task, signals)

    assert calls == [(False, False)]


@pytest.mark.parametrize(
    ("source_mode", "wav_enabled", "error"),
    [
        ("remote_snapshot", False, "资源包发现仅支持本地客户端资源"),
        ("local_path", True, "resource pack 当前不支持 WAV 转码"),
    ],
)
def test_resource_pack_wad_snapshot_is_rejected_before_app_context(
    monkeypatch,
    source_mode: str,
    wav_enabled: bool,
    error: str,
) -> None:
    """直接构造的 WAD snapshot 也必须在创建上下文前通过 local/WAV 边界。"""
    ref = ResourcePackWadRef("Game/DATA/FINAL/Legacy.wad.client", size=12, mtime_ns=34)
    task = _build_task(
        source_mode=source_mode,
        run_mapping=False,
        wav_enabled=wav_enabled,
        resource_pack_wads=(ref,),
    )
    calls: list[str] = []
    signals = SimpleNamespace(progress=SimpleNamespace(emit=lambda _payload: None))
    monkeypatch.setattr(
        task_runner,
        "create_app_context",
        lambda **_kwargs: calls.append("context") or pytest.fail("不应创建 AppContext"),
    )

    with pytest.raises(ValueError, match=error):
        task_runner.run_execution_task(task, signals)

    assert calls == []
