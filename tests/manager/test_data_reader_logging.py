"""DataReader 日志治理测试。"""

from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.manager.data_reader as data_reader_module
from lol_audio_unpack.manager.data_reader import DataReader


def test_write_unknown_categories_to_file_logs_error_with_exception(monkeypatch, tmp_path: Path) -> None:
    """写未知分类文件失败时应以带异常的 error 记录。"""
    reader = DataReader.__new__(DataReader)
    reader.unknown_categories = {"CAT_A"}
    reader.unknown_categories_file = tmp_path / "unknown-category.txt"

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(data_reader_module, "logger", SimpleNamespace(
        info=lambda _message: None,
        opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
    ))
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))

    reader.write_unknown_categories_to_file()

    assert opt_calls == [{"exception": True}]
    assert errors == ["写入未知分类文件时出错: disk full"]


def test_validate_data_version_major_mismatch_does_not_emit_parse_error(monkeypatch) -> None:
    """大版本不匹配应只记录 critical 并抛错，不再追加解析错误日志。"""
    reader = DataReader.__new__(DataReader)
    reader.version = "16.3"
    reader.data = {"metadata": {"gameVersion": "15.14"}}

    criticals: list[str] = []
    errors: list[str] = []

    monkeypatch.setattr(
        data_reader_module,
        "logger",
        SimpleNamespace(
            warning=lambda _message: None,
            error=errors.append,
            critical=criticals.append,
            opt=lambda **_kwargs: SimpleNamespace(error=errors.append),
        ),
    )

    with pytest.raises(ValueError, match="大版本不同"):
        reader._validate_data_version()

    assert len(criticals) == 1
    assert "当前游戏版本: 16.3" in criticals[0]
    assert errors == []


def test_validate_data_version_parse_failure_logs_error_with_exception(monkeypatch) -> None:
    """版本号解析失败时应以带异常的 error 记录。"""
    reader = DataReader.__new__(DataReader)
    reader.version = "16.bad"
    reader.data = {"metadata": {"gameVersion": "16.14"}}

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(
        data_reader_module,
        "logger",
        SimpleNamespace(
            warning=lambda _message: None,
            error=errors.append,
            critical=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    reader._validate_data_version()

    assert opt_calls == [{"exception": True}]
    assert errors == ["解析版本号时出错。当前游戏: '16.bad', 数据文件: '16.14'"]


def test_get_champion_banks_logs_error_with_exception_on_unexpected_failure(monkeypatch) -> None:
    """英雄 banks 读取入口遇到非预期异常时应显式记录错误并返回 None。"""
    reader = DataReader.__new__(DataReader)
    reader.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    reader.champion_banks_dir = Path("/virtual/champions")
    reader._champion_banks_cache = {}

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(
        data_reader_module,
        "logger",
        SimpleNamespace(
            info=lambda _message: None,
            warning=lambda _message: None,
            error=errors.append,
            critical=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )
    monkeypatch.setattr(data_reader_module, "read_data", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = reader.get_champion_banks(1)

    assert result is None
    assert opt_calls == [{"exception": True}]
    assert errors == ["读取英雄 banks 数据失败: champion_id=1"]


def test_get_map_events_logs_error_with_exception_on_unexpected_failure(monkeypatch) -> None:
    """地图 events 读取入口遇到非预期异常时应显式记录错误并返回 None。"""
    reader = DataReader.__new__(DataReader)
    reader.ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    reader.map_events_dir = Path("/virtual/maps")
    reader._map_events_cache = {}

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(
        data_reader_module,
        "logger",
        SimpleNamespace(
            info=lambda _message: None,
            warning=lambda _message: None,
            error=errors.append,
            critical=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )
    monkeypatch.setattr(data_reader_module, "read_data", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = reader.get_map_events(11)

    assert result is None
    assert opt_calls == [{"exception": True}]
    assert errors == ["读取地图 events 数据失败: map_id=11"]
