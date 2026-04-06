"""验证共享 WAD 运行时访问器的行为。"""

from pathlib import Path

import pytest

from lol_audio_unpack.runtime import wad as runtime_wad

pytestmark = pytest.mark.unit


def test_get_wad_reuses_cached_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """启用缓存时，相同路径的 WAD 实例应被复用。"""
    created: list[Path] = []

    class FakeWAD:
        def __init__(self, wad_path: Path) -> None:
            self.path = wad_path
            created.append(wad_path)

    monkeypatch.setattr(runtime_wad, "WAD", FakeWAD)

    wad_path = tmp_path / "voice.wad.client"
    cache: dict[Path, FakeWAD] = {}

    first = runtime_wad.get_wad(wad_path, cache=cache, lock=None)
    second = runtime_wad.get_wad(wad_path, cache=cache, lock=None)

    assert first is second
    assert created == [wad_path]
