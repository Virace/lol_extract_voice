from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.manager import bin_source as m_bin_source
from lol_audio_unpack.manager import bin_updater as m_bin_updater
from lol_audio_unpack.manager import champion_bin_processor as m_champion_processor
from lol_audio_unpack.manager import map_bin_processor as m_map_processor
from lol_audio_unpack.manager.update_result import UpdateEntityResult, UpdateStatus
from lol_audio_unpack.utils.run_summary import get_or_create_run_summary

pytestmark = pytest.mark.unit


def _build_bin_source(tmp_path: Path) -> m_bin_source.BinSource:
    """构造用于单测的最小 `BinSource` 实例。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        仅初始化当前测试所需字段的 `BinSource` 对象。
    """
    source = m_bin_source.BinSource.__new__(m_bin_source.BinSource)
    source.ctx = SimpleNamespace(config=SimpleNamespace(game_path=tmp_path, dev_mode=False), paths=SimpleNamespace())
    source.game_path = tmp_path
    source.use_local_bin_flag_file = tmp_path / ".use_local_bin"
    source.local_bin_input_dir = tmp_path / "bin_input"
    source.local_bin_input_dir.mkdir(parents=True, exist_ok=True)
    return source


def test_extract_bin_raws_prefers_wad_when_wad_exists(tmp_path, monkeypatch):
    """验证存在 WAD 文件时优先从 WAD 提取 BIN 原始数据。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    calls = []

    class FakeWAD:
        def __init__(self, path):
            self.path = Path(path)

        def extract(self, bin_paths, raw):
            calls.append((self.path, list(bin_paths), raw))
            return [b"from-wad"]

    monkeypatch.setattr(m_bin_source, "WAD", FakeWAD)

    wad_path = tmp_path / "Annie.wad.client"
    wad_path.write_bytes(b"")

    result = source._extract_bin_raws(
        wad_path=wad_path,
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert calls == [(wad_path, ["data/characters/Annie/skins/skin0001.bin"], True)]
    assert result == [b"from-wad"]


def test_extract_bin_raws_reads_local_files_when_flag_enabled(tmp_path):
    """验证启用本地 BIN 模式后会直接读取本地文件。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    target_file = source.local_bin_input_dir / "data/characters/Annie/skins/skin0001.bin"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"from-local")

    result = source._extract_bin_raws(
        wad_path=tmp_path / "missing.wad.client",
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == [b"from-local"]


def test_extract_bin_raws_logs_fallback_to_local_bin_when_wad_missing(tmp_path, monkeypatch):
    """验证 WAD 缺失但启用本地 BIN 模式时会输出回退诊断日志。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    target_file = source.local_bin_input_dir / "data/characters/Annie/skins/skin0001.bin"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"from-local")

    debug_messages: list[str] = []
    trace_messages: list[str] = []
    monkeypatch.setattr(
        m_bin_source,
        "logger",
        SimpleNamespace(
            debug=lambda message: debug_messages.append(str(message)),
            trace=lambda message: trace_messages.append(str(message)),
            warning=lambda _message: None,
        ),
    )

    missing_wad = tmp_path / "missing.wad.client"
    result = source._extract_bin_raws(
        wad_path=missing_wad,
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == [b"from-local"]
    assert debug_messages == [f"英雄 1 (annie) 的WAD文件不可用，回退到本地BIN模式: {missing_wad}"]
    assert any(str(source.local_bin_input_dir) in message for message in trace_messages)


def test_extract_bin_raws_raises_when_flag_enabled_but_entity_dir_missing(tmp_path):
    """验证启用本地 BIN 模式但实体目录缺失时会抛出异常。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="本地BIN实体目录不存在"):
        source._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["data/characters/Annie/skins/skin0001.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("data/characters/Annie"),
        )


def test_extract_bin_raws_returns_empty_when_local_mode_disabled(tmp_path):
    """验证未启用本地 BIN 模式时缺失 WAD 会返回空结果。"""
    source = _build_bin_source(tmp_path)

    result = source._extract_bin_raws(
        wad_path=tmp_path / "missing.wad.client",
        bin_paths=["data/characters/Annie/skins/skin0001.bin"],
        entity_label="英雄 1 (annie)",
        local_required_dir=Path("data/characters/Annie"),
    )

    assert result == []


def test_extract_bin_raws_raises_when_local_bin_root_missing(tmp_path):
    """验证本地 BIN 根目录缺失时会抛出异常。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")
    source.local_bin_input_dir.rmdir()

    with pytest.raises(FileNotFoundError, match="目录不存在"):
        source._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["data/characters/Annie/skins/skin0001.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("data/characters/Annie"),
        )


def test_extract_bin_raws_raises_for_path_traversal(tmp_path):
    """验证越界路径会被拒绝处理。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="越界"):
        source._extract_bin_raws(
            wad_path=tmp_path / "missing.wad.client",
            bin_paths=["../../outside.bin"],
            entity_label="英雄 1 (annie)",
            local_required_dir=Path("."),
        )


def test_extract_bin_raws_allows_partial_missing_and_keeps_order(tmp_path):
    """验证部分 BIN 缺失时仍保持原始顺序返回结果。"""
    source = _build_bin_source(tmp_path)
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    base_dir = source.local_bin_input_dir / "data/characters/Annie/skins"
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "skin0001.bin").write_bytes(b"first")
    (base_dir / "skin0003.bin").write_bytes(b"third")

    result = source._extract_bin_raws(
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


def test_process_champion_skins_reports_missing_bin_as_failure_input(tmp_path, monkeypatch):
    """验证没有可用 bank 引用时不再静默返回成功。"""
    processor = m_champion_processor.ChampionBinProcessor.__new__(m_champion_processor.ChampionBinProcessor)
    processor.ctx = SimpleNamespace(config=SimpleNamespace(game_path=tmp_path, dev_mode=False), paths=SimpleNamespace())
    processor.force_update = False
    processor.process_events = False
    processor.version = "16.3"
    processor.game_path = tmp_path
    processor.champion_banks_dir = tmp_path / "banks" / "champions"
    processor.champion_events_dir = tmp_path / "events" / "champions"
    processor.bin_source = SimpleNamespace(_extract_bin_raws=lambda *args, **kwargs: [None, b"fallback"])

    monkeypatch.setattr(m_champion_processor, "needs_update", lambda *args, **kwargs: True)

    write_calls = []
    monkeypatch.setattr(m_champion_processor, "write_data", lambda *args, **kwargs: write_calls.append(True))

    champion_data = {
        "alias": "Annie",
        "skins": [
            {"id": "1", "isBase": True, "binPath": "data/characters/Annie/skins/skin0001.bin"},
            {"id": "2", "isBase": False, "binPath": "data/characters/Annie/skins/skin0002.bin"},
        ],
        "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
    }

    with pytest.raises(ValueError, match="未提取到可用 bank 引用"):
        processor._process_champion_skins(champion_data, "1")

    assert write_calls == []


def test_load_map_bin_file_reads_local_bin_when_available(tmp_path, monkeypatch):
    """验证地图 BIN 可用时优先读取本地文件内容。"""
    source = _build_bin_source(tmp_path)
    source.game_path = tmp_path
    source.use_local_bin_flag_file.write_text("", encoding="utf-8")

    local_file = source.local_bin_input_dir / "data/maps/shipping/map11/map11.bin"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(b"map-bin")

    class FakeBIN:
        def __init__(self, raw):
            self.raw = raw

    monkeypatch.setattr(m_bin_source, "BIN", FakeBIN)

    result = source._load_map_bin_file(
        "11",
        {
            "binPath": "data/maps/shipping/map11/map11.bin",
            "wad": {"root": "Game/DATA/Maps/Map11.wad.client"},
        },
    )

    assert isinstance(result, FakeBIN)
    assert result.raw == b"map-bin"


def test_update_includes_common_map_in_targeted_scope(tmp_path, monkeypatch):
    """验证精确地图更新由核心层自动包含 Map 0。"""
    updater = m_bin_updater.BinUpdater.__new__(m_bin_updater.BinUpdater)
    updater.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={}, paths=SimpleNamespace())
    updater.force_update = False
    updater.process_events = True
    updater.version = "16.3"
    updater.data_file_base = tmp_path / "data"
    updater.languages = []
    updater.bin_source = SimpleNamespace(languages=[], _is_local_bin_mode_enabled=lambda: False)
    map_updates: list[dict] = []

    def update_maps(data: dict) -> tuple[UpdateEntityResult, ...]:
        map_updates.append(data)
        return tuple(UpdateEntityResult.success("map", map_id) for map_id in data["maps"])

    updater._map_processor = SimpleNamespace(languages=[], _update_maps=update_maps)

    monkeypatch.setattr(
        m_bin_updater,
        "read_data",
        lambda *args, **kwargs: {
            "metadata": {"languages": ["zh_CN"]},
            "maps": {"0": {"id": 0}, "33": {"id": 33}},
        },
    )

    results = updater.update(target="map", map_ids=["33"])

    assert list(map_updates[0]["maps"]) == ["0", "33"]
    assert [result.entity_id for result in results] == ["0", "33"]


def test_update_logs_stage_start_and_summary_for_targeted_mode(tmp_path, monkeypatch):
    """验证 BinUpdater 顶层会输出精确模式开始和完成摘要。"""
    updater = m_bin_updater.BinUpdater.__new__(m_bin_updater.BinUpdater)
    updater.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={}, paths=SimpleNamespace())
    updater.force_update = False
    updater.process_events = True
    updater.version = "16.3"
    updater.data_file_base = tmp_path / "data"
    updater.languages = []
    updater.bin_source = SimpleNamespace(languages=[], _is_local_bin_mode_enabled=lambda: True)
    updater._champion_processor = SimpleNamespace(
        _update_champions=lambda _data: (UpdateEntityResult.success("champion", "1"),)
    )
    updater._map_processor = SimpleNamespace(
        languages=[],
        _update_maps=lambda _data: (
            UpdateEntityResult.success("map", "0"),
            UpdateEntityResult.success("map", "11"),
        ),
    )

    info_messages: list[str] = []
    success_messages: list[str] = []

    monkeypatch.setattr(
        m_bin_updater,
        "read_data",
        lambda *args, **kwargs: {
            "metadata": {"languages": ["zh_CN"]},
            "champions": {"1": {"alias": "Annie"}},
            "maps": {"0": {"id": 0}, "11": {"id": 11}},
        },
    )
    monkeypatch.setattr(
        m_bin_updater,
        "logger",
        SimpleNamespace(
            info=lambda message: info_messages.append(str(message)),
            success=lambda message: success_messages.append(str(message)),
        ),
    )
    updater.update(target="all", champion_ids=["1"], map_ids=["11"])

    assert info_messages == ["开始更新 BIN 数据（精确模式）：英雄 1 个，地图 2 个，事件处理=开启，本地BIN模式=开启"]
    assert success_messages == ["BinUpdater 更新完成（精确模式）：英雄 1 个，地图 2 个"]


def test_bin_updater_completion_does_not_report_partial_as_success(monkeypatch) -> None:
    """逐实体不完整时只能记录 warning 摘要。"""
    warning_messages: list[str] = []
    success_messages: list[str] = []
    monkeypatch.setattr(
        m_bin_updater,
        "logger",
        SimpleNamespace(
            warning=warning_messages.append,
            success=success_messages.append,
        ),
    )

    m_bin_updater.BinUpdater._log_completion(
        [UpdateEntityResult.incomplete("map", "11", message="事件绑定不完整")],
        mode="精确模式",
        champion_count=0,
        map_count=1,
    )

    assert success_messages == []
    assert warning_messages == ["BinUpdater 更新完成（精确模式）：英雄 0 个，地图 1 个，部分成功 1 个，失败 0 个"]


def test_update_filters_hidden_champions_only_in_batch_mode(tmp_path, monkeypatch):
    """验证默认批量排除特殊英雄，但精确模式仍允许显式处理。"""
    updater = m_bin_updater.BinUpdater.__new__(m_bin_updater.BinUpdater)
    updater.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False), runtime_cache={}, paths=SimpleNamespace())
    updater.force_update = False
    updater.process_events = True
    updater.version = "16.16"
    updater.data_file_base = tmp_path / "data"
    updater.languages = []
    updater.bin_source = SimpleNamespace(languages=[], _is_local_bin_mode_enabled=lambda: False)

    champion_updates: list[dict] = []
    map_updates: list[dict] = []

    def update_champions(data: dict) -> tuple[UpdateEntityResult, ...]:
        champion_updates.append(data)
        return tuple(UpdateEntityResult.success("champion", champion_id) for champion_id in data["champions"])

    def update_maps(data: dict) -> tuple[UpdateEntityResult, ...]:
        map_updates.append(data)
        return tuple(UpdateEntityResult.success("map", map_id) for map_id in data["maps"])

    updater._champion_processor = SimpleNamespace(_update_champions=update_champions)
    updater._map_processor = SimpleNamespace(languages=[], _update_maps=update_maps)

    monkeypatch.setattr(
        m_bin_updater,
        "read_data",
        lambda *args, **kwargs: {
            "metadata": {"languages": ["zh_CN"]},
            "champions": {
                "1": {"id": 1, "alias": "Annie", "wad": {"root": "Champions/Annie.wad.client"}},
                "60001": {
                    "id": 60001,
                    "alias": "Jade_Annie",
                    "wad": {"root": "Champions/Jade_Annie.wad.client"},
                },
            },
            "maps": {"11": {"id": 11}},
        },
    )

    updater.update(target="all")

    assert list(champion_updates[0]["champions"]) == ["1"]
    assert champion_updates[0]["maps"] == {"11": {"id": 11}}
    assert map_updates[0]["maps"] == {"11": {"id": 11}}

    updater.update(target="skin", champion_ids=["60001"])

    assert list(champion_updates[1]["champions"]) == ["60001"]


def test_process_single_map_records_note_when_common_dedup_removes_all_events(tmp_path, monkeypatch):
    """验证公共事件去重清空结果时会记录可解释差异。"""
    processor = m_map_processor.MapBinProcessor.__new__(m_map_processor.MapBinProcessor)
    processor.ctx = SimpleNamespace(
        config=SimpleNamespace(game_path=tmp_path, dev_mode=False),
        runtime_cache={},
        paths=SimpleNamespace(),
    )
    processor.force_update = False
    processor.process_events = True
    processor.version = "16.3"
    processor.languages = []
    processor.map_banks_dir = tmp_path / "banks" / "maps"
    processor.map_events_dir = tmp_path / "events" / "maps"

    fake_bin = SimpleNamespace(
        theme_music=None,
        data=[
            SimpleNamespace(
                music=None,
                bank_units=[
                    SimpleNamespace(
                        events=[SimpleNamespace(string="Play_Map33_SFX_Start")],
                        category="AMB_SFX",
                        bank_path=None,
                    )
                ],
            )
        ],
    )

    processor.bin_source = SimpleNamespace(
        _load_map_bin_file=lambda *_args, **_kwargs: fake_bin,
        _create_base_data=lambda _id, _type, **payload: payload,
    )

    monkeypatch.setattr(m_map_processor, "needs_update", lambda *args, **kwargs: True)
    monkeypatch.setattr(m_map_processor, "write_data", lambda *args, **kwargs: tmp_path / "artifact.msgpack")
    monkeypatch.setattr(
        processor,
        "_reference_map_banks",
        lambda _references: {"AMB_SFX": [["assets/sounds/wwise2016/amb.bnk"]]},
    )

    processor._process_single_map(
        "33",
        {
            "binPath": "data/maps/shipping/map33/map33.bin",
            "names": {"default": "Map33"},
        },
        {"Play_Map33_SFX_Start": {"地图 0/AMB_SFX"}},
        set(),
    )

    summary = get_or_create_run_summary(processor.ctx.runtime_cache)
    assert any(
        "地图 33 (Map33) 的事件在与 地图 0 的公共事件去重后为空" in note for note in summary.stages["update"].notes
    )
    assert any("category=AMB_SFX" in detail for detail in summary.stages["update"].debug_details)


def test_update_champions_logs_simple_progress_messages(tmp_path, monkeypatch):
    """验证英雄批量更新会输出简单的日志进度提示。"""
    processor = m_champion_processor.ChampionBinProcessor.__new__(m_champion_processor.ChampionBinProcessor)
    processor.ctx = SimpleNamespace(
        config=SimpleNamespace(game_path=tmp_path, dev_mode=False),
        runtime_cache={},
        paths=SimpleNamespace(),
    )
    processor.champion_banks_dir = tmp_path / "banks" / "champions"
    processor.champion_events_dir = tmp_path / "events" / "champions"
    progress_events = []
    processor._progress_callback = progress_events.append
    processed_ids: list[str] = []
    info_messages: list[str] = []
    success_messages: list[str] = []

    monkeypatch.setattr(
        m_champion_processor,
        "logger",
        SimpleNamespace(
            info=lambda message: info_messages.append(str(message)),
            success=lambda message: success_messages.append(str(message)),
        ),
    )
    monkeypatch.setattr(
        processor,
        "_process_champion_skins",
        lambda _champion_data, champion_id: (
            processed_ids.append(champion_id),
            UpdateEntityResult.success("champion", champion_id),
        )[1],
    )

    processor._update_champions({"champions": {"2": {}, "1": {}}})

    assert processed_ids == ["1", "2"]
    assert "处理英雄进度 1/2: 1" in info_messages
    assert "处理英雄进度 2/2: 2" in info_messages
    assert success_messages == ["英雄Banks数据更新完成，共处理 2 个英雄"]
    assert [(event.event, event.current, event.total) for event in progress_events] == [
        ("started", 0, 2),
        ("advanced", 1, 2),
        ("advanced", 2, 2),
        ("finished", 2, 2),
    ]


def test_update_maps_logs_simple_progress_messages(tmp_path, monkeypatch):
    """验证地图批量更新会输出简单的日志进度提示。"""
    processor = m_map_processor.MapBinProcessor.__new__(m_map_processor.MapBinProcessor)
    processor.ctx = SimpleNamespace(
        config=SimpleNamespace(game_path=tmp_path, dev_mode=False),
        runtime_cache={},
        paths=SimpleNamespace(),
    )
    processor.map_banks_dir = tmp_path / "banks" / "maps"
    processor.map_events_dir = tmp_path / "events" / "maps"
    progress_events = []
    processor._progress_callback = progress_events.append
    processed_ids: list[str] = []
    info_messages: list[str] = []
    success_messages: list[str] = []

    monkeypatch.setattr(
        m_map_processor,
        "logger",
        SimpleNamespace(
            info=lambda message: info_messages.append(str(message)),
            success=lambda message: success_messages.append(str(message)),
            debug=lambda _message: None,
            opt=lambda **_kwargs: SimpleNamespace(error=lambda _message: None),
        ),
    )
    monkeypatch.setattr(
        processor,
        "_process_single_map",
        lambda map_id, *_args: (
            processed_ids.append(map_id),
            UpdateEntityResult.success("map", map_id),
        )[1],
    )

    processor._update_maps({"maps": {"11": {"name": "Map11"}, "12": {"name": "Map12"}}})

    assert processed_ids == ["11", "12"]
    assert "处理地图进度 1/2: 11" in info_messages
    assert "处理地图进度 2/2: 12" in info_messages
    assert success_messages == ["地图Banks数据更新完成，共处理 2 个地图"]
    assert [(event.event, event.current, event.total) for event in progress_events] == [
        ("started", 0, 2),
        ("advanced", 1, 2),
        ("advanced", 2, 2),
        ("finished", 2, 2),
    ]


def test_update_champions_keeps_processing_after_one_entity_fails(tmp_path, monkeypatch):
    """验证逐实体失败进入 typed result，后续英雄仍会继续处理。"""
    processor = m_champion_processor.ChampionBinProcessor.__new__(m_champion_processor.ChampionBinProcessor)
    processor.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    processor.champion_banks_dir = tmp_path / "banks" / "champions"
    processor.champion_events_dir = tmp_path / "events" / "champions"
    processor._progress_callback = None

    def process(_data: dict, champion_id: str) -> UpdateEntityResult:
        if champion_id == "1":
            raise ValueError("missing bank")
        return UpdateEntityResult.success("champion", champion_id)

    monkeypatch.setattr(processor, "_process_champion_skins", process)

    results = processor._update_champions({"champions": {"1": {}, "2": {}}})

    assert [result.status for result in results] == [UpdateStatus.FAILED, UpdateStatus.SUCCESS]
    assert results[0].error_message == "missing bank"
