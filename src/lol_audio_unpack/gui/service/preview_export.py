"""试听音频默认 WAV 位置的路径装配。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.runtime.wav import build_output_path


def resolve_wav_path(
    wem_path: str | Path,
    *,
    audio_root: str | Path,
    wav_root: str | Path,
) -> Path:
    """按正式 WAV 输出镜像规则推导试听音频的默认 WAV 路径。

    Args:
        wem_path: 当前试听音频的 ``.wem`` 路径。
        audio_root: 当前版本 ``audios/<version>`` 根目录。
        wav_root: 当前版本 ``wavs/<version>`` 根目录。

    Returns:
        默认镜像 ``.wav`` 路径。
    """
    return build_output_path(
        Path(wem_path),
        audio_root=Path(audio_root),
        wav_root=Path(wav_root),
    )
