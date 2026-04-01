"""解包阶段接入 WAV sidecar 的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack import unpack

pytestmark = pytest.mark.unit


def test_persisted_wem_is_submitted_to_sidecar(tmp_path: Path) -> None:
    submitted: list[Path] = []

    class FakeCoordinator:
        def submit_persisted_wem(self, wem_path: Path, **_kwargs) -> None:
            submitted.append(wem_path)

    file = SimpleNamespace(save_file=lambda path: Path(path).write_bytes(b"wem-bytes"))
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    unpack._persist_wem_and_maybe_submit(file, destination, wav_submitter=FakeCoordinator().submit_persisted_wem)

    assert submitted == [destination]


def test_failed_wem_write_is_not_submitted(tmp_path: Path) -> None:
    submitted: list[Path] = []

    def boom(_path: Path) -> None:
        raise OSError("disk full")

    file = SimpleNamespace(save_file=boom)
    destination = tmp_path / "audios" / "15.8" / "champions" / "1" / "VO" / "123.wem"

    with pytest.raises(OSError):
        unpack._persist_wem_and_maybe_submit(file, destination, wav_submitter=submitted.append)

    assert submitted == []
