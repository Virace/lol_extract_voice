"""兼容层：迁移期保留旧 WAV runtime 导入路径。"""

from lol_audio_unpack.runtime.wav._runtime import (
    AttemptResult,
    WavJob,
    WavJobFailure,
    WavSidecarSummary,
    _run_attempt_with_timeout,
    build_wav_output_path,
    default_worker_entry,
    resolve_wav_decode_config,
)

__all__ = [
    "WavJob",
    "WavJobFailure",
    "WavSidecarSummary",
    "build_wav_output_path",
    "default_worker_entry",
    "resolve_wav_decode_config",
    "AttemptResult",
    "_run_attempt_with_timeout",
]
