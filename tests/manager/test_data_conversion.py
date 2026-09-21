"""验证离线格式转换的无损边界与失败保留合同。"""

import msgpack
import pytest
from ruamel.yaml.error import YAMLError

from lol_audio_unpack.manager.errors import SharedDataCorruptError
from lol_audio_unpack.manager.files import find_data_file, needs_update, read_data, write_data
from scripts import convert_data as converter

pytestmark = pytest.mark.unit

@pytest.mark.parametrize("dev_mode", [False, True])
def test_legacy_file_is_not_read_or_used_after_corruption(tmp_path, dev_mode):
    """同名旧文件不改变权威输入，损坏不能伪装为空数据。"""
    base = tmp_path / "data"
    legacy = base.with_suffix(".yml")
    legacy.write_text("old: true\n", encoding="utf-8")
    assert find_data_file(base, dev_mode=dev_mode) is None
    assert read_data(base, dev_mode=dev_mode) == {}
    write_data({"current": True}, base, dev_mode=dev_mode)
    assert read_data(legacy, dev_mode=dev_mode) == {"current": True}
    base.with_suffix(".msgpack").write_bytes(b"\xc1")
    with pytest.raises(SharedDataCorruptError):
        read_data(base, dev_mode=dev_mode)
    assert needs_update(base, "16.18", False, dev_mode=dev_mode)
    assert legacy.read_text(encoding="utf-8") == "old: true\n"


@pytest.mark.parametrize(
    ("format_name", "payload"),
    [("yaml", {1: b"raw bytes", "1": [None, True, 1.25]}), ("json", {"items": [1, "中文", None]})],
)
def test_conversion_roundtrip_preserves_project_types(tmp_path, format_name, payload):
    """真实数据类型往返后保持键与二进制身份。"""
    source = tmp_path / "source.msgpack"
    source.write_bytes(msgpack.packb(payload, use_bin_type=True))
    text_file = tmp_path / f"readable.{format_name}"
    target = tmp_path / "restored.msgpack"
    converter.convert(source, text_file, source_format="msgpack", target_format=format_name)
    converter.convert(text_file, target, source_format=format_name, target_format="msgpack")
    assert msgpack.unpackb(target.read_bytes(), raw=False, strict_map_key=False) == payload


@pytest.mark.parametrize("payload", [{1: "integer key"}, {"binary": b"wem"}])
def test_json_rejects_lossy_types_without_publishing(tmp_path, payload):
    """JSON 不能直接表示的类型必须报错，不悄悄转换。"""
    source = tmp_path / "source.msgpack"
    source.write_bytes(msgpack.packb(payload, use_bin_type=True))
    target = tmp_path / "target.json"
    with pytest.raises(ValueError, match="JSON"):
        converter.convert(source, target, source_format="msgpack", target_format="json")
    assert not target.exists()
    assert source.is_file()


def test_existing_target_and_failed_publish_preserve_files(tmp_path, monkeypatch):
    """已有文件与发布失败均不留下正式半成品。"""
    source = tmp_path / "source.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    target = tmp_path / "target.msgpack"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        converter.convert(source, target, source_format="json", target_format="msgpack")
    assert target.read_bytes() == b"original"
    failed = tmp_path / "failed.msgpack"
    monkeypatch.setattr(converter.os, "link", lambda *_: (_ for _ in ()).throw(OSError("publish failed")))
    with pytest.raises(OSError, match="publish failed"):
        converter.convert(source, failed, source_format="json", target_format="msgpack")
    assert not failed.exists()
    assert set(tmp_path.glob(".*.tmp")) == set()


@pytest.mark.parametrize("text", ["!!python/object/apply:os.system ['echo unsafe']", "key: 1\nkey: 2\n"])
def test_yaml_rejects_object_construction_and_duplicate_keys(tmp_path, text):
    """旧 YAML 只安全读取数据，重复键不隐式丢失。"""
    source = tmp_path / "old.yaml"
    source.write_text(text, encoding="utf-8")
    target = tmp_path / "target.msgpack"
    with pytest.raises(YAMLError):
        converter.convert(source, target, source_format="yaml", target_format="msgpack")
    assert not target.exists()
