"""GUI 数据链日志治理测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import lol_audio_unpack.gui.service.data_loader as data_loader_module
import lol_audio_unpack.gui.service.worker as worker_module
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader
from lol_audio_unpack.gui.service.worker import DataLoadWorker


def _build_loader() -> EntityDataLoader:
    """构造最小 `EntityDataLoader` 实例。"""
    return EntityDataLoader.__new__(EntityDataLoader)


def test_entity_data_loader_logs_warning_with_exception_on_init_failure(monkeypatch) -> None:
    """初始化失败时应以带异常的 warning 记录，并继续向上抛出。"""
    loader = _build_loader()
    opt_calls: list[dict[str, object]] = []
    warnings: list[str] = []

    monkeypatch.setattr(loader, "_load_raw_entities", lambda _entity_type: ("16.3", []))
    monkeypatch.setattr(
        loader,
        "_ensure_bank_dataset_ready",
        lambda _entity_type: (_ for _ in ()).throw(RuntimeError("init boom")),
    )
    monkeypatch.setattr(
        data_loader_module,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(warning=warnings.append),
        ),
    )

    with pytest.raises(RuntimeError, match="init boom"):
        loader.load_entities("champions")

    assert opt_calls == [{"exception": True}]
    assert warnings == ["Error initializing data for champions: init boom"]


def test_entity_data_loader_logs_warning_with_exception_on_row_failure(monkeypatch) -> None:
    """单个实体构建失败但继续时应以带异常的 warning 记录。"""
    loader = _build_loader()
    opt_calls: list[dict[str, object]] = []
    warnings: list[str] = []

    monkeypatch.setattr(loader, "_load_raw_entities", lambda _entity_type: ("16.3", [{"id": 1}, {"id": 2}]))
    monkeypatch.setattr(loader, "_ensure_bank_dataset_ready", lambda _entity_type: None)

    def _build_entity_row(_entity_type: str, entity_dict: dict[str, object], _version: str) -> dict[str, object]:
        if entity_dict["id"] == 1:
            raise RuntimeError("row boom")
        return {"id": entity_dict["id"]}

    monkeypatch.setattr(loader, "_build_entity_row", _build_entity_row)
    monkeypatch.setattr(
        data_loader_module,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(warning=warnings.append),
        ),
    )

    result = loader.load_entities_by_ids("champions", ("1", "2"))

    assert result == [{"id": 2}]
    assert opt_calls == [{"exception": True}]
    assert warnings == ["Error loading entity 1: row boom"]


def test_data_load_worker_logs_info_for_expected_shared_data_error(monkeypatch) -> None:
    """预期的共享数据控制流异常应保持 info，不升级为 error。"""
    infos: list[str] = []
    error_payloads: list[str] = []

    class FakeLoader:
        def __init__(self, _app_context) -> None:
            pass

        def load_entities(self, _entity_type: str) -> list[dict]:
            raise RuntimeError("请先运行更新程序")

    monkeypatch.setattr(worker_module, "EntityDataLoader", FakeLoader)
    monkeypatch.setattr(
        worker_module,
        "logger",
        SimpleNamespace(
            debug=lambda _message: None,
            info=infos.append,
            opt=lambda **_kwargs: SimpleNamespace(error=lambda _message: None),
        ),
    )

    worker = DataLoadWorker(SimpleNamespace(), "champions")
    worker.error.connect(error_payloads.append)
    worker.run()

    assert infos == ["champions 共享实体数据暂不可用，交由后续流程决定是否自动准备: 请先运行更新程序"]
    assert error_payloads == ["请先运行更新程序"]


def test_data_load_worker_logs_error_with_exception_for_unexpected_error(monkeypatch) -> None:
    """非预期异常应以带异常的 error 记录。"""
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []
    error_payloads: list[str] = []

    class FakeLoader:
        def __init__(self, _app_context) -> None:
            pass

        def load_entities(self, _entity_type: str) -> list[dict]:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "EntityDataLoader", FakeLoader)
    monkeypatch.setattr(
        worker_module,
        "logger",
        SimpleNamespace(
            debug=lambda _message: None,
            info=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    worker = DataLoadWorker(SimpleNamespace(), "champions")
    worker.error.connect(error_payloads.append)
    worker.run()

    assert opt_calls == [{"exception": True}]
    assert errors == ["champions 实体扫描失败: boom"]
    assert error_payloads == ["boom"]
