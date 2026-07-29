"""`utils.common` 公开行为基线测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import msgpack
import pytest

import lol_audio_unpack.utils.common as common_utils
from lol_audio_unpack.utils.common import Singleton, format_duration, sanitize_filename


def test_sanitize_filename_replaces_windows_illegal_chars() -> None:
    """非法字符应被替换为下划线。"""

    assert sanitize_filename("a<b>:c?.wem") == "a_b__c_.wem"


def test_format_duration_keeps_human_readable_thresholds() -> None:
    """耗时格式化应保持当前阈值行为。"""

    assert format_duration(800) == "800ms"
    assert format_duration(1500) == "1.5s (1500ms)"


def test_singleton_metaclass_reuses_instance() -> None:
    """同一类型的重复构造应复用实例。"""

    class Sample(metaclass=Singleton):
        """测试用单例类型。"""

    try:
        assert Sample() is Sample()
    finally:
        Singleton._instances.pop(Sample, None)


@pytest.mark.parametrize("format_name", ["json", "msgpack", "yaml"])
def test_structured_loaders_log_parse_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    format_name: str,
) -> None:
    """结构化文件解析失败时应记录异常并返回空映射。"""
    path = tmp_path / f"broken.{format_name}"
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []
    monkeypatch.setattr(
        common_utils,
        "logger",
        SimpleNamespace(
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    if format_name == "json":
        path.write_text("{}", encoding="utf-8")
        parse_error: Exception = json.JSONDecodeError("bad json", "{}", 0)
        monkeypatch.setattr(common_utils.json, "load", lambda _file: (_ for _ in ()).throw(parse_error))
        result = common_utils.load_json(path)
        expected = f"JSON 解析错误，位置: {path}, 错误: {parse_error}"
    elif format_name == "msgpack":
        path.write_bytes(b"broken")
        parse_error = msgpack.exceptions.UnpackException("bad pack")
        monkeypatch.setattr(
            common_utils.msgpack,
            "load",
            lambda _file, raw=False: (_ for _ in ()).throw(parse_error),
        )
        result = common_utils.load_msgpack(path)
        expected = f"MessagePack 解析错误，位置: {path}, 错误: {parse_error}"
    else:
        path.write_text("a: 1\n", encoding="utf-8")
        parse_error = RuntimeError("bad yaml")

        class BrokenYaml:
            """模拟始终解析失败的 YAML 加载器。"""

            def load(self, _file):
                """抛出预设解析异常。"""
                raise parse_error

        monkeypatch.setattr(common_utils, "YAML", lambda *args, **kwargs: BrokenYaml())
        result = common_utils.load_yaml(path)
        expected = f"加载 YAML 文件时出错: {path}, 错误: {parse_error}"

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [expected]
