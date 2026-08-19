"""试听音频右键导出服务测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.gui.service.preview_export import resolve_wav_path, transcode_wav


def test_resolve_wav_path_mirrors_audio_tree(tmp_path: Path) -> None:
    audio_root = tmp_path / "audios" / "15.10"
    wav_root = tmp_path / "wavs" / "15.10"
    wem_path = audio_root / "champions" / "1" / "VO" / "1001.wem"

    result = resolve_wav_path(wem_path, audio_root=audio_root, wav_root=wav_root)

    assert result == wav_root / "champions" / "1" / "VO" / "1001.wav"


def test_resolve_wav_path_keeps_duplicate_wem_ids_in_their_exact_paths(tmp_path: Path) -> None:
    audio_root = tmp_path / "audios" / "15.10"
    wav_root = tmp_path / "wavs" / "15.10"
    first_wem = audio_root / "champions" / "1" / "1000" / "VO" / "1001.wem"
    second_wem = audio_root / "champions" / "1" / "1001" / "VO" / "1001.wem"

    first_wav = resolve_wav_path(first_wem, audio_root=audio_root, wav_root=wav_root)
    second_wav = resolve_wav_path(second_wem, audio_root=audio_root, wav_root=wav_root)

    assert first_wav == wav_root / "champions" / "1" / "1000" / "VO" / "1001.wav"
    assert second_wav == wav_root / "champions" / "1" / "1001" / "VO" / "1001.wav"


def test_transcode_wav_uses_requested_format(tmp_path: Path) -> None:
    wem_path = tmp_path / "1001.wem"
    wav_path = tmp_path / "1001.wav"
    calls: list[tuple[Path, Path, object]] = []

    def fake_decode(in_path, out_path, *, config):
        calls.append((Path(in_path), Path(out_path), config))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"RIFF....WAVE")
        return SimpleNamespace(output_path=Path(out_path))

    result = transcode_wav(wem_path, wav_path, wav_format="pcm16", decode_fn=fake_decode)

    assert result == wav_path.resolve()
    assert calls[0][0] == wem_path.resolve()
    assert calls[0][1] == wav_path.resolve()
    assert getattr(calls[0][2], "sample_format", None) is not None
