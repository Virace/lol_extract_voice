"""`utils.common` 日志治理测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import msgpack

import lol_audio_unpack.utils.common as common_utils


def test_load_json_logs_error_with_exception_on_decode_failure(tmp_path: Path, monkeypatch) -> None:
    """JSON 解析失败时应以带异常的 error 记录。"""
    path = tmp_path / "broken.json"
    path.write_text("{}", encoding="utf-8")

    decode_error = json.JSONDecodeError("bad json", "{}", 0)
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(common_utils.json, "load", lambda _file: (_ for _ in ()).throw(decode_error))
    monkeypatch.setattr(
        common_utils,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    result = common_utils.load_json(path)

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [f"JSON 解析错误，位置: {path}, 错误: {decode_error}"]


def test_load_msgpack_logs_error_with_exception_on_unpack_failure(tmp_path: Path, monkeypatch) -> None:
    """MessagePack 解析失败时应以带异常的 error 记录。"""
    path = tmp_path / "broken.msgpack"
    path.write_bytes(b"broken")

    unpack_error = msgpack.exceptions.UnpackException("bad pack")
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(common_utils.msgpack, "load", lambda _file, raw=False: (_ for _ in ()).throw(unpack_error))
    monkeypatch.setattr(
        common_utils,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    result = common_utils.load_msgpack(path)

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [f"MessagePack 解析错误，位置: {path}, 错误: {unpack_error}"]


def test_load_yaml_logs_error_with_exception_on_loader_failure(tmp_path: Path, monkeypatch) -> None:
    """YAML 加载失败时应以带异常的 error 记录。"""
    path = tmp_path / "broken.yml"
    path.write_text("a: 1\n", encoding="utf-8")

    yaml_error = RuntimeError("bad yaml")
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    class BrokenYaml:
        def load(self, _file):
            raise yaml_error

    monkeypatch.setattr(common_utils, "YAML", lambda *args, **kwargs: BrokenYaml())
    monkeypatch.setattr(
        common_utils,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    result = common_utils.load_yaml(path)

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [f"加载 YAML 文件时出错: {path}, 错误: {yaml_error}"]
