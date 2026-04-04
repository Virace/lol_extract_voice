"""验证 runtime.wav 包公开导出面的回归测试。"""

from importlib import import_module

import pytest

pytestmark = pytest.mark.unit


def test_runtime_wav_package_exports_stable_public_api() -> None:
    """验证 runtime.wav 包导出了稳定公开能力。"""
    runtime_wav = import_module("lol_audio_unpack.runtime.wav")

    assert runtime_wav.__all__ == [
        "AttemptResult",
        "Job",
        "JobFailure",
        "JobHandle",
        "JobSpec",
        "ManifestRecorder",
        "TranscodeCoordinator",
        "TranscodeProgress",
        "TranscodeSummary",
        "build_job_spec",
        "build_output_path",
        "build_recorder",
        "launch_detached",
        "launch_job",
        "parse_job_spec",
        "resolve_decode_config",
        "run_job",
        "run_worker",
    ]
