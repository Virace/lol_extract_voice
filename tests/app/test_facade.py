"""`app.facade` 中 WAV 进度标签桥接的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.app.facade as facade_module
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.types import OperationOptions, SourceMode, WavOutputOptions


def test_transcode_wav_passes_entity_display_labels_to_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """独立 WAV stage 应将实体列表式名称传给 runtime 作为展示标签。"""
    app = LolAudioUnpackApp(SimpleNamespace())
    reader = SimpleNamespace(version="15.8")
    audio_root = tmp_path / "audios" / "15.8" / "champions" / "103-ahri"
    audio_root.mkdir(parents=True, exist_ok=True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(app, "_create_reader", lambda: reader)
    monkeypatch.setattr(
        app,
        "_build_entity_data",
        lambda *_args, **_kwargs: SimpleNamespace(entity_name="阿狸", entity_title="九尾妖狐"),
    )
    monkeypatch.setattr(app, "_resolve_audio_paths", lambda _entity_data: (audio_root,))
    monkeypatch.setattr(
        facade_module,
        "run_tree",
        lambda **kwargs: captured.update(kwargs) or {"status": "success"},
    )

    app.transcode_wav(
        OperationOptions(
            champion_ids=(103,),
            wav_output=WavOutputOptions(enabled=True),
        )
    )

    audio_targets = captured["audio_targets"]
    assert isinstance(audio_targets, tuple)
    assert len(audio_targets) == 1
    assert audio_targets[0].root_path == audio_root
    assert audio_targets[0].display_label == "阿狸·九尾妖狐"


def test_extract_runs_explicit_champions_and_maps_without_dropping_either_target(monkeypatch) -> None:
    """显式英雄与地图同时传入时，两个解包分支都应执行。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            include_types=("VO",),
            exclude_types=(),
            output_path=Path("output"),
            game_region="zh_CN",
        )
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[int]]] = []
    reader = SimpleNamespace()
    monkeypatch.setattr(app, "_create_reader", lambda: reader)
    monkeypatch.setattr(
        facade_module,
        "unpack_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(
        facade_module,
        "unpack_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])),
    )

    app.extract(
        OperationOptions(
            champion_ids=(1,),
            map_ids=(11,),
            special_targets=("champion:66600",),
        )
    )

    assert calls == [("champions", [1, 66600]), ("maps", [11])]


def test_mapping_runs_explicit_champions_and_maps_without_dropping_either_target(monkeypatch) -> None:
    """显式英雄与地图同时传入时，两个映射分支都应执行。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            game_region="zh_CN",
        ),
        paths=SimpleNamespace(cache_path=Path("cache"), hash_path=Path("hashes")),
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[int]]] = []
    reader = SimpleNamespace()
    backend = "native"
    monkeypatch.setattr(app, "_create_reader", lambda: reader)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: backend)
    monkeypatch.setattr(
        facade_module,
        "build_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(
        facade_module,
        "build_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])),
    )

    app.mapping(OperationOptions(champion_ids=(1,), map_ids=(11,)))

    assert calls == [("champions", [1]), ("maps", [11])]


def test_facade_rejects_remote_special_targets_before_resource_preparation() -> None:
    """门面直接调用也必须在远端资源准备前拒绝特殊内容。"""
    app = LolAudioUnpackApp(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.REMOTE_SNAPSHOT)))

    with pytest.raises(ValueError, match="特殊内容仅支持本地客户端资源"):
        app.extract(OperationOptions(special_targets=("champion:66600",)))
