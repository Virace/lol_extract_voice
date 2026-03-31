"""DataReader 日志治理测试。"""

from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace

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
