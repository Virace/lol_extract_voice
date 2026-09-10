"""验证共享 WAD 运行时访问器的行为。"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

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


def test_resolve_bound_wad_rejects_symlink_escape(tmp_path: Path) -> None:
    """binding WAD 经 symlink 解析后不得越出游戏根目录。"""
    game_root = tmp_path / "game"
    wad_dir = game_root / "Game"
    wad_dir.mkdir(parents=True)
    outside = tmp_path / "outside.wad.client"
    outside.write_bytes(b"wad")
    link = wad_dir / "escape.wad.client"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前 Windows 测试环境不允许创建 symlink")

    with pytest.raises(ValueError, match="越出游戏根目录"):
        runtime_wad.resolve_bound_wad(game_root, "Game/escape.wad.client")


def test_extract_wad_protects_legacy_shared_reader() -> None:
    """旧上游共用游标时，应用适配层保证并发调用的返回内容各自正确。"""
    first = Event()
    second = Event()
    start = Barrier(2)

    class LegacyWad:
        """模拟只支持串行读取的外部 WAD 接口。"""

        def extract(self, paths, **_kwargs):
            """以共享游标表示当前目标，暴露未保护读取的交错结果。"""
            self.current = paths[0]
            if not first.is_set():
                first.set()
                second.wait(0.1)
            else:
                second.set()
            return [self.current.encode()]

    wad = LegacyWad()

    def extract(path: str) -> list[bytes]:
        """同时请求同一读取器中的两个目标。"""
        start.wait(timeout=2)
        return runtime_wad.extract_wad(wad, [path], raw=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(extract, ["first", "second"]))
    assert results == [[b"first"], [b"second"]]
