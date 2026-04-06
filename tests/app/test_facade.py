"""`app.facade` 中 WAV 进度标签桥接的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import lol_audio_unpack.app.facade as facade_module
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.types import OperationOptions, WavOutputOptions


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
