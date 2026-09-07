"""试听音频右键导出服务测试。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.gui.service.preview_export import resolve_wav_path


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
