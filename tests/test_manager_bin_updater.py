from pathlib import Path

import pytest

from lol_audio_unpack.manager import bin_updater as m_bin_updater

pytestmark = pytest.mark.unit


def _build_updater(tmp_path: Path) -> m_bin_updater.BinUpdater:
    updater = m_bin_updater.BinUpdater.__new__(m_bin_updater.BinUpdater)
    updater.use_local_bin_flag_file = tmp_path / ".use_local_bin"
    updater.local_bin_input_dir = tmp_path / "bin_input"
    updater.local_bin_input_dir.mkdir(parents=True, exist_ok=True)
    return updater


def test_extract_bin_raws_prefers_wad_when_wad_exists(tmp_path, monkeypatch):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, bin_paths, raw):
            calls.append((self.path, list(bin_paths), raw))
            return [b"from-wad"]

    monkeypatch.setattr(m_bin_updater, "WAD", FakeWAD)

    wad_path = tmp_path / "Annie.wad.client"
    wad_path.write_bytes(b"")

    result = updater._extract_bin_raws(
        wad_path=wad_path,
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert calls == [(wad_path, ["data/characters/Annie/skins/skin0001.bin"], True)]
    assert result == [b"from-wad"]


def test_extract_bin_raws_reads_local_files_when_flag_enabled(tmp_path):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    target_file = updater.local_bin_input_dir / "data/characters/Annie/skins/skin0001.bin"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"from-local")

    result = updater._extract_bin_raws(
        wad_path=tmp_path / "missing.wad.client",
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == [b"from-local"]


def test_extract_bin_raws_raises_when_flag_enabled_but_entity_dir_missing(tmp_path):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="本地BIN实体目录不存在"):
        updater._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["data/characters/Annie/skins/skin0001.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("data/characters/Annie"),
        )


def test_extract_bin_raws_returns_empty_when_local_mode_disabled(tmp_path):
    updater = _build_updater(tmp_path)

    result = updater._extract_bin_raws(
        wad_path=tmp_path / "missing.wad.client",
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == []


def test_extract_bin_raws_raises_when_local_bin_root_missing(tmp_path):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")
    updater.local_bin_input_dir.rmdir()

    with pytest.raises(FileNotFoundError, match="目录不存在"):
        updater._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["data/characters/Annie/skins/skin0001.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("data/characters/Annie"),
        )


def test_extract_bin_raws_raises_for_path_traversal(tmp_path):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="越界"):
        updater._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["../../outside.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("."),
        )


def test_extract_bin_raws_allows_partial_missing_and_keeps_order(tmp_path):
    updater = _build_updater(tmp_path)
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    base_dir = updater.local_bin_input_dir / "data/characters/Annie/skins"
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "skin0001.bin").write_bytes(b"first")
    (base_dir / "skin0003.bin").write_bytes(b"third")

    result = updater._extract_bin_raws(
        wad_path=tmp_path / "missing.wad.client",
        bin_paths=[
            "data/characters/Annie/skins/skin0001.bin",
            "data/characters/Annie/skins/skin0002.bin",
            "data/characters/Annie/skins/skin0003.bin",
        ],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == [b"first", None, b"third"]


def test_process_champion_skins_skips_when_first_bin_missing(tmp_path, monkeypatch):
    updater = m_bin_updater.BinUpdater.__new__(m_bin_updater.BinUpdater)
    updater.force_update = False
    updater.process_events = False
    updater.version = "16.3"
    updater.game_path = tmp_path
    updater.champion_banks_dir = tmp_path / "banks" / "champions"
    updater.champion_events_dir = tmp_path / "events" / "champions"

    monkeypatch.setattr(m_bin_updater, "needs_update", lambda *args, **kwargs: True)
    monkeypatch.setattr(updater, "_extract_bin_raws", lambda *args, **kwargs: [None, b"fallback"])

    write_calls = []
    monkeypatch.setattr(m_bin_updater, "write_data", lambda *args, **kwargs: write_calls.append(True))

    champion_data = {
        "alias": "Annie",
        "skins": [
            {"id": "1", "isBase": True, "binPath": "data/characters/Annie/skins/skin0001.bin"},
            {"id": "2", "isBase": False, "binPath": "data/characters/Annie/skins/skin0002.bin"},
        ],
        "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
    }

    updater._process_champion_skins(champion_data, "1")

    assert write_calls == []


def test_load_map_bin_file_reads_local_bin_when_available(tmp_path, monkeypatch):
    updater = _build_updater(tmp_path)
    updater.game_path = tmp_path
    updater.use_local_bin_flag_file.write_text("", encoding="utf-8")

    local_file = updater.local_bin_input_dir / "data/maps/shipping/map11/map11.bin"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(b"map-bin")

    class FakeBIN:
        def __init__(self, raw):
            self.raw = raw

    monkeypatch.setattr(m_bin_updater, "BIN", FakeBIN)

    result = updater._load_map_bin_file(
        "11",
        {
            "binPath": "data/maps/shipping/map11/map11.bin",
            "wad": {"root": "Game/DATA/Maps/Map11.wad.client"},
        },
    )

    assert isinstance(result, FakeBIN)
    assert result.raw == b"map-bin"
