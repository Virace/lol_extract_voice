"""兼容层：迁移期保留旧 WAV sidecar 导入路径。"""

from lol_audio_unpack.runtime.wav import (
    WavSidecarProgressSnapshot,
    WavSidecarSummary,
    WavTranscodeCoordinator,
    build_wav_output_path,
    resolve_wav_decode_config,
)
from lol_audio_unpack.runtime.wav._runtime import WavJob, WavJobFailure, default_worker_entry

__all__ = [
    "WavJob",
    "WavJobFailure",
    "WavSidecarProgressSnapshot",
    "WavSidecarSummary",
    "WavTranscodeCoordinator",
    "build_wav_output_path",
    "default_worker_entry",
    "resolve_wav_decode_config",
]
