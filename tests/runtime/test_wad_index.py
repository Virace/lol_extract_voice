"""目标驱动 WAD TOC 索引测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from lol_audio_unpack.model.binding import BindingRole, BindingStatus
from lol_audio_unpack.runtime.wad_index import ResolutionRequest, WadIndex, WadTocCache

pytestmark = pytest.mark.unit

EXPECTED_CANDIDATE_COUNT = 2
QUERY_COUNT = 8


@dataclass
class _Section:
    path_hash: int
    offset: int = 1
    compressed_size: int = 1
    size: int = 1
    sha256: int | None = None


class _FakeWad:
    version = (3, 4)

    def __init__(self, sections: list[_Section], payloads: dict[int, bytes | None]):
        self.files = sections
        self._payloads = payloads
        self.extract_calls: list[int] = []

    def extract_by_section(self, section: _Section, _file_path: str, *, raw: bool) -> bytes | None:
        assert raw is True
        self.extract_calls.append(section.offset)
        return self._payloads.get(section.offset)


def _make_index(  # noqa: PLR0913
    tmp_path: Path,
    specs: dict[str, tuple[list[_Section], dict[int, bytes | None]]],
    *,
    root_names: list[str],
    localized_names: list[str] | None = None,
    cache: WadTocCache | None = None,
    factory_calls: list[str] | None = None,
) -> WadIndex:
    """构造使用 fake WAD 边界的索引。"""
    wad_paths: dict[str, Path] = {}
    for name in specs:
        path = tmp_path / "Game" / "DATA" / "FINAL" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        wad_paths[name] = path

    def factory(path: Path) -> _FakeWad:
        if factory_calls is not None:
            factory_calls.append(path.name)
        sections, payloads = specs[path.name]
        return _FakeWad(sections, payloads)

    toc_cache = cache or WadTocCache(factory)
    if cache is not None:
        cache._wad_factory = factory  # noqa: SLF001 - 测试注入外部解析边界
    return WadIndex(
        tmp_path,
        "zh_CN",
        cache=toc_cache,
        root_wads=[wad_paths[name] for name in root_names],
        localized_wads=[wad_paths[name] for name in localized_names or []],
        hash_path=lambda path: {"data/test.bin": 1, "assets/audio.bnk": 2}[path],
    )


def test_resolve_many_uses_root_then_controlled_localized_fallback(tmp_path: Path) -> None:
    """root 首选仅在缺失时回退当前语言 WAD。"""
    index = _make_index(
        tmp_path,
        {
            "Root.wad.client": ([_Section(2)], {1: b"root-bank"}),
            "Voice.zh_CN.wad.client": ([_Section(1)], {1: b"localized-bin"}),
        },
        root_names=["Root.wad.client"],
        localized_names=["Voice.zh_CN.wad.client"],
    )

    bin_result, bank_result = index.resolve_many(
        [
            ResolutionRequest("data/test.bin", BindingRole.ROOT),
            ResolutionRequest("assets/audio.bnk", BindingRole.ROOT),
        ],
        load_payload=True,
    )

    assert bin_result.status is BindingStatus.RESOLVED
    assert bin_result.role is BindingRole.FALLBACK
    assert bin_result.wad.endswith("Voice.zh_CN.wad.client")
    assert bin_result.payload == b"localized-bin"
    assert bank_result.role is BindingRole.ROOT
    assert bank_result.payload == b"root-bank"


@pytest.mark.parametrize(
    ("second_payload", "expected_status", "expected_wad"),
    [
        (b"same", BindingStatus.AMBIGUOUS_IDENTICAL, "A.wad.client"),
        (b"different", BindingStatus.AMBIGUOUS_CONFLICT, None),
    ],
)
def test_resolve_many_compares_payload_only_for_ambiguous_hashes(
    tmp_path: Path,
    second_payload: bytes,
    expected_status: BindingStatus,
    expected_wad: str | None,
) -> None:
    """同 role 多候选应比较 payload，相同则确定选择、不同则拒绝。"""
    index = _make_index(
        tmp_path,
        {
            "B.wad.client": ([_Section(1, offset=2)], {2: second_payload}),
            "A.wad.client": ([_Section(1, offset=1)], {1: b"same"}),
        },
        root_names=["B.wad.client", "A.wad.client"],
    )

    result = index.resolve_many([ResolutionRequest("data/test.bin", BindingRole.ROOT)], load_payload=True)[0]

    assert result.status is expected_status
    assert result.wad is None if expected_wad is None else result.wad.endswith(expected_wad)
    assert len(result.candidates) == EXPECTED_CANDIDATE_COUNT


def test_toc_cache_reuses_same_stat_key_across_threads(tmp_path: Path) -> None:
    """同一路径/stat/version 的并发查询只构造一次 WAD TOC。"""
    calls: list[str] = []
    index = _make_index(
        tmp_path,
        {"Root.wad.client": ([_Section(2)], {1: b"bank"})},
        root_names=["Root.wad.client"],
        factory_calls=calls,
    )

    def resolve() -> BindingStatus:
        return index.resolve_many([ResolutionRequest("assets/audio.bnk", BindingRole.ROOT)])[0].status

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _index: resolve(), range(QUERY_COUNT)))

    assert statuses == [BindingStatus.RESOLVED] * QUERY_COUNT
    assert calls == ["Root.wad.client"]
    assert index.snapshot_metrics()["cacheHits"] == QUERY_COUNT - 1


def test_localized_preference_does_not_treat_root_payload_as_conflict(tmp_path: Path) -> None:
    """VO 类首选 localized 时，root 只作为 fallback，不参与同 role 冲突。"""
    index = _make_index(
        tmp_path,
        {
            "Root.wad.client": ([_Section(2)], {1: b"root"}),
            "Voice.zh_CN.wad.client": ([_Section(2)], {1: b"localized"}),
        },
        root_names=["Root.wad.client"],
        localized_names=["Voice.zh_CN.wad.client"],
    )

    result = index.resolve_many([ResolutionRequest("assets/audio.bnk", BindingRole.LOCALIZED)])[0]

    assert result.status is BindingStatus.RESOLVED
    assert result.role is BindingRole.LOCALIZED
    assert result.wad.endswith("Voice.zh_CN.wad.client")


def test_resolve_many_reports_missing_and_unique_extract_failure(tmp_path: Path) -> None:
    """无候选与唯一 entry 解压失败应分别落到 missing/parse_failed。"""
    index = _make_index(
        tmp_path,
        {"Root.wad.client": ([_Section(1)], {1: None})},
        root_names=["Root.wad.client"],
    )

    parse_failed, missing = index.resolve_many(
        [
            ResolutionRequest("data/test.bin", BindingRole.ROOT),
            ResolutionRequest("assets/audio.bnk", BindingRole.ROOT),
        ],
        load_payload=True,
    )

    assert parse_failed.status is BindingStatus.PARSE_FAILED
    assert missing.status is BindingStatus.MISSING


def test_discovery_includes_root_and_current_region_but_excludes_other_locales(tmp_path: Path) -> None:
    """候选枚举只能纳入 root 与当前语言 WAD。"""
    final_root = tmp_path / "Game" / "DATA" / "FINAL" / "Champions"
    final_root.mkdir(parents=True)
    for name in ["Test.wad.client", "Test.zh_CN.wad.client", "Test.en_US.wad.client"]:
        (final_root / name).write_bytes(name.encode())

    index = WadIndex(tmp_path, "zh_CN")

    assert [path.name for path in index.root_wads] == ["Test.wad.client"]
    assert [path.name for path in index.localized_wads] == ["Test.zh_CN.wad.client"]


def test_toc_cache_invalidates_when_file_stat_changes(tmp_path: Path) -> None:
    """物理 WAD size/mtime 变化后不得复用旧 TOC。"""
    path = tmp_path / "Game" / "DATA" / "FINAL" / "Test.wad.client"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"first")
    calls: list[int] = []

    def factory(_path: Path) -> _FakeWad:
        calls.append(_path.stat().st_size)
        return _FakeWad([], {})

    cache = WadTocCache(factory)
    first, first_hit = cache.get(tmp_path, path)
    path.write_bytes(b"second-version")
    second, second_hit = cache.get(tmp_path, path)

    assert first.format_version == "3.4"
    assert second.format_version == "3.4"
    assert first_hit is False
    assert second_hit is False
    assert calls == [len(b"first"), len(b"second-version")]
