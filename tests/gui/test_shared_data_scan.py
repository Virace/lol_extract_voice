"""共享实体目录 typed scan 与 worker 边界测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.service.data_loader as data_loader_module
import lol_audio_unpack.gui.service.worker as worker_module
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader, build_scan_failure_result
from lol_audio_unpack.gui.service.worker import SharedDataScanWorker
from lol_audio_unpack.gui.shared_data import (
    SharedDataProblemCode,
    SharedDataReadiness,
    SharedDataScanResult,
)
from lol_audio_unpack.manager.errors import (
    ResourceSchemaMismatchError,
    SharedDataCorruptError,
    SharedDataMissingError,
)
from lol_audio_unpack.model.binding import RESOURCE_SCHEMA_VERSION

pytestmark = pytest.mark.unit

EXPECTED_REQUIRED_COUNT = 2
FAILING_CHAMPION_ID = 2
WORKER_GENERATION = 10


def _champion(entity_id: int, alias: str) -> dict:
    """构造最小普通英雄 metadata。"""
    return {
        "id": entity_id,
        "alias": alias,
        "names": {"zh_CN": alias},
        "wad": {"root": f"Champions/{alias}.wad.client"},
    }


def _map(entity_id: int) -> dict:
    """构造最小地图 metadata。"""
    return {
        "id": entity_id,
        "names": {"zh_CN": f"Map {entity_id}"},
        "wad": {"root": f"Maps/{entity_id}.wad.client"},
    }


def _build_loader(monkeypatch, *, champions: list[dict], maps: list[dict]) -> EntityDataLoader:
    """构造只保留目录扫描边界的轻量 loader。"""
    loader = EntityDataLoader.__new__(EntityDataLoader)
    loader.ctx = SimpleNamespace(
        config=SimpleNamespace(dev_mode=False, game_path=Path("C:/Game")),
        game_region="zh_CN",
    )
    loader.data_reader = SimpleNamespace(
        version="16.16",
        get_champions=lambda: champions,
        get_maps=lambda: maps,
    )
    monkeypatch.setattr(loader, "_ensure_bank_dataset_ready", lambda _entity_type: None)
    monkeypatch.setattr(loader, "_preload_bank_artifact", lambda _entity_type, _entity_id: None)
    monkeypatch.setattr(
        loader,
        "_build_entity_row",
        lambda entity_type, entity, _version: {
            "id": str(entity["id"]),
            "name": str(entity.get("alias") or entity["id"]),
            "entity_type": entity_type,
        },
    )
    monkeypatch.setattr(loader, "load_resource_pack_rows", lambda **_kwargs: [])
    monkeypatch.setattr(
        loader,
        "_build_special_row",
        lambda _champion, _version, *, display_name: {
            "id": "66600",
            "key": "champion:66600",
            "name": display_name or "Urgot",
            "audio": "未准备",
            "mapping": "未准备",
        },
    )
    return loader


def test_scan_catalog_complete_ignores_unprepared_optional_special(monkeypatch) -> None:
    """必需目录完整时，可选特殊内容未准备不能降级 ready。"""
    champions = [
        _champion(1, "Annie"),
        _champion(2, "Olaf"),
        {
            "id": 66600,
            "alias": "Ruby_Urgot",
            "wad": {"root": "Champions/Ruby_Urgot.wad.client"},
        },
    ]
    loader = _build_loader(monkeypatch, champions=champions, maps=[_map(0), _map(11)])
    progress_events = []

    result = loader.scan_catalog(4, progress=progress_events.append)

    assert result.readiness is SharedDataReadiness.COMPLETE
    assert result.summary.champion_expected == EXPECTED_REQUIRED_COUNT
    assert result.summary.champion_loaded == EXPECTED_REQUIRED_COUNT
    assert result.summary.map_loaded == EXPECTED_REQUIRED_COUNT
    assert result.summary.special_discovered == 1
    assert result.summary.special_unprepared == 1
    assert result.special.unprepared_ids == ("champion:66600",)
    assert [(event.stage_key, event.event, event.current, event.total) for event in progress_events] == [
        ("champions", "started", 0, 2),
        ("champions", "advanced", 1, 2),
        ("champions", "advanced", 2, 2),
        ("champions", "finished", 2, 2),
        ("special", "started", 0, None),
        ("special", "advanced", 1, None),
        ("special", "finished", 1, 1),
        ("maps", "started", 0, 2),
        ("maps", "advanced", 1, 2),
        ("maps", "advanced", 2, 2),
        ("maps", "finished", 2, 2),
    ]


def test_scan_catalog_single_schema_failure_is_partial_and_aggregated(monkeypatch) -> None:
    """单个普通实体旧 schema 必须形成 partial 与聚合问题。"""
    loader = _build_loader(
        monkeypatch,
        champions=[_champion(1, "Annie"), _champion(2, "Olaf")],
        maps=[_map(0), _map(11)],
    )
    original_builder = loader._build_entity_row

    def build_row(entity_type: str, entity: dict, version: str) -> dict:
        if entity_type == "champions" and entity["id"] == FAILING_CHAMPION_ID:
            raise ResourceSchemaMismatchError("old schema")
        return original_builder(entity_type, entity, version)

    monkeypatch.setattr(loader, "_build_entity_row", build_row)

    result = loader.scan_catalog(5)

    assert result.readiness is SharedDataReadiness.PARTIAL
    assert result.summary.champion_loaded == 1
    assert result.summary.champion_failed == 1
    problem = next(problem for problem in result.problems if problem.scope == "champions")
    assert problem.code is SharedDataProblemCode.RESOURCE_SCHEMA_MISMATCH
    assert problem.entity_ids == ("2",)
    assert result.all_blocking_problems_repairable is True


def test_scan_catalog_logs_schema_mismatches_once_without_tracebacks(monkeypatch) -> None:
    """同根因旧 schema 只形成一条扫描摘要，不逐实体记录 traceback。"""
    loader = _build_loader(
        monkeypatch,
        champions=[_champion(1, "Annie"), _champion(2, "Olaf")],
        maps=[_map(0), _map(11)],
    )
    original_builder = loader._build_entity_row

    def build_row(entity_type: str, entity: dict, version: str) -> dict:
        if entity_type == "champions":
            raise ResourceSchemaMismatchError("old schema")
        return original_builder(entity_type, entity, version)

    monkeypatch.setattr(loader, "_build_entity_row", build_row)
    info_messages: list[str] = []
    opt_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        data_loader_module,
        "logger",
        SimpleNamespace(
            info=info_messages.append,
            warning=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=lambda _message: None),
        ),
    )

    result = loader.scan_catalog(5)

    assert result.readiness is SharedDataReadiness.FAILED
    assert opt_calls == []
    assert len(info_messages) == 1
    assert "champions expected=2 loaded=0 failed=2" in info_messages[0]


def test_scan_catalog_all_required_section_failures_are_failed(monkeypatch) -> None:
    """任一必需目录完全不可读时不能降级为 partial。"""
    loader = _build_loader(
        monkeypatch,
        champions=[_champion(1, "Annie")],
        maps=[_map(0), _map(11)],
    )
    monkeypatch.setattr(
        loader,
        "_build_entity_row",
        lambda entity_type, entity, _version: (
            (_ for _ in ()).throw(SharedDataMissingError("missing"))
            if entity_type == "champions"
            else {"id": str(entity["id"])}
        ),
    )

    result = loader.scan_catalog(6)

    assert result.readiness is SharedDataReadiness.FAILED
    assert result.summary.champion_loaded == 0
    assert result.summary.map_loaded == EXPECTED_REQUIRED_COUNT


def test_scan_catalog_requires_map_zero(monkeypatch) -> None:
    """metadata 未声明 Map 0 时，即使其余地图都可读也必须 failed。"""
    loader = _build_loader(
        monkeypatch,
        champions=[_champion(1, "Annie")],
        maps=[_map(11)],
    )

    result = loader.scan_catalog(7)

    assert result.readiness is SharedDataReadiness.FAILED
    assert SharedDataProblemCode.MAP_COMMON_MISSING in {problem.code for problem in result.problems}


def test_scan_catalog_empty_required_metadata_is_failed(monkeypatch) -> None:
    """可读但为空的必需 metadata 不能成为成功 no-op。"""
    loader = _build_loader(monkeypatch, champions=[], maps=[])

    result = loader.scan_catalog(8)

    assert result.readiness is SharedDataReadiness.FAILED
    assert SharedDataProblemCode.DATASET_EMPTY in {problem.code for problem in result.problems}


def test_scan_failure_result_classifies_corrupt_dataset_without_text_matching() -> None:
    """reader 初始化损坏应保留 artifact_corrupt typed code。"""
    result = build_scan_failure_result(9, SharedDataCorruptError("broken"))

    assert result.readiness is SharedDataReadiness.FAILED
    assert result.problems[0].code is SharedDataProblemCode.ARTIFACT_CORRUPT


def test_preload_bank_artifact_suppresses_per_item_read_traceback(monkeypatch, tmp_path: Path) -> None:
    """逐实体预检由扫描层聚合，read_data 必须关闭当前边界错误日志。"""
    loader = EntityDataLoader.__new__(EntityDataLoader)
    loader.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    loader.data_reader = SimpleNamespace(
        champion_banks_dir=tmp_path,
        map_banks_dir=tmp_path,
        _champion_banks_cache={},
        _map_banks_cache={},
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(data_loader_module, "find_data_file", lambda *_args, **_kwargs: tmp_path / "1.msgpack")

    def read_artifact(*_args, **kwargs) -> dict:
        captured.update(kwargs)
        return {"resourceSchemaVersion": RESOURCE_SCHEMA_VERSION - 1}

    monkeypatch.setattr(data_loader_module, "read_data", read_artifact)

    with pytest.raises(ResourceSchemaMismatchError):
        loader._preload_bank_artifact("champions", "1")

    assert captured["log_errors"] is False


def test_scan_worker_emits_one_typed_result_and_progress(monkeypatch) -> None:
    """完整扫描 worker 应把结果与进度保持在同一 generation。"""
    ctx = SimpleNamespace()
    expected = build_scan_failure_result(WORKER_GENERATION, SharedDataMissingError("missing"))

    class FakeLoader:
        def __init__(self, _ctx) -> None:
            pass

        def scan_catalog(self, generation: int, *, progress) -> SharedDataScanResult:
            progress(SimpleNamespace(generation=generation, stage_key="champions"))
            return expected

    monkeypatch.setattr(worker_module, "EntityDataLoader", FakeLoader)
    finished = []
    progress_events = []
    errors = []
    worker = SharedDataScanWorker(ctx, WORKER_GENERATION)
    worker.finished.connect(finished.append)
    worker.progress.connect(progress_events.append)
    worker.error.connect(errors.append)

    worker.run()

    assert finished == [expected]
    assert progress_events[0].generation == WORKER_GENERATION
    assert errors == []


def test_scan_worker_returns_typed_result_for_expected_init_failure(monkeypatch) -> None:
    """缺失 dataset 仍走 finished typed result，不退化为字符串 error。"""
    ctx = SimpleNamespace()

    class FakeLoader:
        def __init__(self, _ctx) -> None:
            raise SharedDataMissingError("missing")

    monkeypatch.setattr(worker_module, "EntityDataLoader", FakeLoader)
    finished = []
    errors = []
    worker = SharedDataScanWorker(ctx, 11)
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)

    worker.run()

    assert finished[0].problems[0].code is SharedDataProblemCode.DATASET_MISSING
    assert errors == []


def test_scan_worker_emits_typed_problem_for_unexpected_failure(monkeypatch) -> None:
    """无法形成扫描结果的程序错误才使用 worker-level typed error。"""
    ctx = SimpleNamespace()

    class FakeLoader:
        def __init__(self, _ctx) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "EntityDataLoader", FakeLoader)
    monkeypatch.setattr(
        worker_module,
        "logger",
        SimpleNamespace(
            debug=lambda _message: None,
            info=lambda *_args: None,
            opt=lambda **_kwargs: SimpleNamespace(error=lambda _message: None),
        ),
    )
    finished = []
    errors = []
    worker = SharedDataScanWorker(ctx, 12)
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)

    worker.run()

    assert finished == []
    assert errors[0].code is SharedDataProblemCode.UNEXPECTED
