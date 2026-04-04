import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.types import RemoteSnapshotConfig, SourceMode
from lol_audio_unpack.manager import utils as mutils

pytestmark = pytest.mark.unit


def test_find_data_file_priority_in_dev_mode(tmp_path):
    base = tmp_path / "data"
    (base.with_suffix(".json")).write_text("{}", encoding="utf-8")
    (base.with_suffix(".yml")).write_text("k: v\n", encoding="utf-8")
    (base.with_suffix(".msgpack")).write_bytes(b"dummy")

    assert mutils.find_data_file(base, dev_mode=True).suffix == ".yml"


def test_find_data_file_priority_in_prod_mode(tmp_path):
    base = tmp_path / "data"
    (base.with_suffix(".json")).write_text("{}", encoding="utf-8")
    (base.with_suffix(".yml")).write_text("k: v\n", encoding="utf-8")
    (base.with_suffix(".msgpack")).write_bytes(b"dummy")

    assert mutils.find_data_file(base, dev_mode=False).suffix == ".msgpack"


def test_write_and_read_data_roundtrip_msgpack(tmp_path):
    base = tmp_path / "result" / "data"
    base.parent.mkdir(parents=True, exist_ok=True)
    data = {"metadata": {"gameVersion": "16.3"}, "items": [1, 2, 3]}

    mutils.write_data(data, base, dev_mode=False)

    assert base.with_suffix(".msgpack").exists()
    assert mutils.read_data(base, dev_mode=False) == data


def test_write_and_read_data_roundtrip_yaml(tmp_path):
    base = tmp_path / "result" / "data"
    base.parent.mkdir(parents=True, exist_ok=True)
    data = {"metadata": {"gameVersion": "16.3"}, "items": [1, 2, 3]}

    mutils.write_data(data, base, dev_mode=True)

    assert base.with_suffix(".yml").exists()
    assert mutils.read_data(base, dev_mode=True) == data


def test_get_game_version_success(tmp_path):
    game_path = tmp_path / "game"
    meta_file = game_path / "Game" / "content-metadata.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps({"version": "16.3.123.456"}), encoding="utf-8")

    assert mutils.get_game_version(game_path) == "16.3"


def test_get_game_version_invalid_version(tmp_path):
    game_path = tmp_path / "game"
    meta_file = game_path / "Game" / "content-metadata.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps({"version": "invalid"}), encoding="utf-8")

    with pytest.raises(ValueError):
        mutils.get_game_version(game_path)


def test_get_lcu_version_success(tmp_path):
    game_path = tmp_path / "game"
    exe_path = game_path / "LeagueClient" / "LeagueClient.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_payload = (
        b"prefix"
        + "ProductVersion".encode("utf-16le")
        + b"\x00\x00"
        + "16.5.751.1533".encode("utf-16le")
        + b"\x00\x00suffix"
    )
    exe_path.write_bytes(exe_payload)

    assert mutils.get_lcu_version(game_path) == "16.5"


def test_resolve_context_version_uses_remote_snapshot_version():
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.REMOTE_SNAPSHOT,
            remote_snapshot=RemoteSnapshotConfig(
                version="16.5",
                lcu_manifest_url="https://example.com/lcu.manifest",
                game_manifest_url="https://example.com/game.manifest",
            ),
            game_path=Path("unused-game-root"),
        ),
        runtime_cache={},
    )

    assert mutils.resolve_context_version(ctx) == "16.5"
    assert ctx.runtime_cache["resolved_runtime_version"] == "16.5"


def test_create_metadata_object():
    result = mutils.create_metadata_object("16.3", ["default", "zh_CN"])

    metadata = result["metadata"]
    assert metadata["gameVersion"] == "16.3"
    assert metadata["scriptName"] == "lol-audio-unpack"
    assert metadata["languages"] == ["default", "zh_CN"]
    assert "scriptVersion" in metadata
    assert "createdAt" in metadata


def test_needs_update_behavior(tmp_path):
    base = tmp_path / "manifest" / "data"
    base.parent.mkdir(parents=True, exist_ok=True)

    # 文件不存在时需要更新
    assert mutils.needs_update(base, "16.3", force_update=False, dev_mode=False) is True

    # 版本一致时不需要更新
    mutils.write_data({"metadata": {"gameVersion": "16.3"}}, base, dev_mode=False)
    assert mutils.needs_update(base, "16.3", force_update=False, dev_mode=False) is False

    # 版本不一致时需要更新
    assert mutils.needs_update(base, "16.4", force_update=False, dev_mode=False) is True

    # 强制更新始终为True
    assert mutils.needs_update(base, "16.3", force_update=True, dev_mode=False) is True


def test_read_data_logs_error_with_exception_when_loader_fails(tmp_path, monkeypatch):
    base = tmp_path / "broken"
    actual_file = base.with_suffix(".json")
    actual_file.write_text("{}", encoding="utf-8")

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(mutils, "find_data_file", lambda _path, dev_mode=False: actual_file)
    monkeypatch.setattr(mutils, "load_json", lambda _path: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        mutils,
        "logger",
        SimpleNamespace(
            trace=lambda _message: None,
            debug=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    result = mutils.read_data(base, dev_mode=False)

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [f"读取文件时出错: {actual_file}, 错误: boom"]


def test_write_data_logs_error_with_exception_when_dump_fails(tmp_path, monkeypatch):
    base = tmp_path / "out" / "data"
    base.parent.mkdir(parents=True, exist_ok=True)
    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(mutils, "dump_msgpack", lambda _data, _path: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        mutils,
        "logger",
        SimpleNamespace(
            trace=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    mutils.write_data({"k": "v"}, base, dev_mode=False)

    assert opt_calls == [{"exception": True}]
    assert errors == [f"写入文件失败: {base.with_suffix('.msgpack')}, 错误: boom"]
