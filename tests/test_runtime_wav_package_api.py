"""验证 runtime.wav 包公开导出面的回归测试。"""

from importlib import import_module

import pytest

pytestmark = pytest.mark.unit


def test_runtime_wav_package_exports_stable_public_api() -> None:
    """验证 runtime.wav 包导出了稳定公开能力。"""
    runtime_wav = import_module("lol_audio_unpack.runtime.wav")

    assert runtime_wav.__all__ == [
        "WavBackgroundJobSpec",
        "WavBackgroundProcessHandle",
        "WavManifestRecorder",
        "WavSidecarProgressSnapshot",
        "WavSidecarSummary",
        "WavTranscodeCoordinator",
        "build_manifest_recorder",
        "build_wav_background_job_spec_from_paths",
        "build_wav_output_path",
        "launch_detached_wav",
        "launch_wav_background_process",
        "resolve_wav_decode_config",
        "run_wav_background_job",
    ]


def test_legacy_wav_modules_remain_runtime_shims() -> None:
    """验证旧 WAV 入口只是 runtime.wav 的兼容层。"""
    legacy_sidecar = import_module("lol_audio_unpack.wav_sidecar")
    runtime_wav = import_module("lol_audio_unpack.runtime.wav")

    assert legacy_sidecar.WavTranscodeCoordinator is runtime_wav.WavTranscodeCoordinator
    assert legacy_sidecar.WavSidecarProgressSnapshot is runtime_wav.WavSidecarProgressSnapshot
