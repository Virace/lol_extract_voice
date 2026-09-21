"""验证后端预检的真实样本合同与故障归属。"""

from __future__ import annotations

import struct
import sys
import wave
from pathlib import Path
from threading import Event

import pytest

from lol_audio_unpack.runtime.probe import probe_tool, validate_wav
from lol_audio_unpack.runtime.tool_process import ToolError, run_tool

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("tool", ["hirc", "wav"])
def test_bundled_sample_passes_builtin(tool: str, tmp_path: Path) -> None:
    """包资源经真实内置入口得到可用音频或结构化关系。"""
    result = probe_tool(tool, scratch_root=tmp_path)
    assert result.success, result.detail


def test_probe_distinguishes_missing_tool_environment_and_cancel(tmp_path: Path) -> None:
    """只有外部文件失败允许切内置；环境失败和取消不能被重试掩盖。"""
    missing = str(tmp_path / "missing.exe")
    result = probe_tool("wav", path=missing, scratch_root=tmp_path / "scratch")
    assert result.kind == "path"
    assert result.can_fallback
    blocked = tmp_path / "file"
    blocked.write_bytes(b"not a directory")
    result = probe_tool("wav", path=missing, scratch_root=blocked)
    assert result.kind == "environment"
    assert not result.can_fallback
    cancel = Event()
    cancel.set()
    result = probe_tool("wav", path=missing, scratch_root=tmp_path, cancel=cancel)
    assert result.kind == "cancelled"
    assert not result.can_fallback


@pytest.mark.parametrize("sample_width", [2, 3])
def test_wav_validation_accepts_extra_chunks_and_rejects_truncation(tmp_path: Path, sample_width: int) -> None:
    """合法容器差异与自身声明不自洽的输出必须区分。"""
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, sample_width, 8000, 0, "NONE", "not compressed"))
        writer.writeframes(b"\0" * sample_width * 81)
    original = path.read_bytes()
    junk = b"JUNK" + struct.pack("<I", 4) + b"test"
    changed = original[:4] + struct.pack("<I", len(original) + len(junk) - 8) + original[8:12] + junk + original[12:]
    path.write_bytes(changed)
    validate_wav(path)
    path.write_bytes(changed[:-1])
    with pytest.raises(ValueError, match="截断"):
        validate_wav(path)


@pytest.mark.parametrize(
    ("script", "timeout", "kind", "detail"),
    [
        ("import sys; print('specific failure'); sys.exit(7)", 5, "exit", "specific failure"),
        ("import time; time.sleep(30)", 0.1, "timeout", "超过"),
    ],
)
def test_external_process_returns_actual_failure(script: str, timeout: float, kind: str, detail: str) -> None:
    """非零退出保留原诊断，超时真实终止本次子进程。"""
    with pytest.raises(ToolError) as raised:
        run_tool([sys.executable, "-c", script], timeout=timeout)
    assert raised.value.kind == kind
    assert detail in str(raised.value)
