"""试听音频单文件 WAV 导出服务。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyvgmstream import decode_to_wav_file

from lol_audio_unpack.runtime.wav import build_output_path, resolve_decode_config


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


def transcode_wav(
    wem_path: str | Path,
    wav_path: str | Path,
    *,
    wav_format: str = "pcm16",
    decode_fn: Callable[..., Any] = decode_to_wav_file,
) -> Path:
    """把单个试听 ``.wem`` 转码为 ``.wav``。

    Args:
        wem_path: 输入 ``.wem`` 路径。
        wav_path: 输出 ``.wav`` 路径。
        wav_format: WAV 输出格式，沿用现有 ``auto/pcm16/pcm24/pcm32/float`` 语义。
        decode_fn: 解码函数，供测试替换。

    Returns:
        实际写出的 ``.wav`` 路径。
    """
    output = Path(wav_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = decode_fn(
        Path(wem_path).expanduser().resolve(),
        output,
        config=resolve_decode_config(wav_format),
    )
    return Path(getattr(result, "output_path", output))
