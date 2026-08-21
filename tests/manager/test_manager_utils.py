"""manager 数据文件与 metadata 辅助函数的行为测试。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.manager.files as mfiles
from lol_audio_unpack.app import game_version
from lol_audio_unpack.app.types import RemoteSnapshotConfig, SourceMode
from lol_audio_unpack.manager import utils as mutils
from lol_audio_unpack.manager.errors import ArtifactWriteError

pytestmark = pytest.mark.unit


def test_find_data_file_priority_in_dev_mode(tmp_path):
    base = tmp_path / "data"
    (base.with_suffix(".json")).write_text("{}", encoding="utf-8")
    (base.with_suffix(".yml")).write_text("k: v\n", encoding="utf-8")
    (base.with_suffix(".msgpack")).write_bytes(b"dummy")

    assert mfiles.find_data_file(base, dev_mode=True).suffix == ".yml"


def test_find_data_file_priority_in_prod_mode(tmp_path):
    base = tmp_path / "data"
    (base.with_suffix(".json")).write_text("{}", encoding="utf-8")
    (base.with_suffix(".yml")).write_text("k: v\n", encoding="utf-8")
    (base.with_suffix(".msgpack")).write_bytes(b"dummy")

    assert mfiles.find_data_file(base, dev_mode=False).suffix == ".msgpack"


def test_write_and_read_data_roundtrip_msgpack(tmp_path):
    base = tmp_path / "result" / "data"
    data = {"metadata": {"gameVersion": "16.3"}, "items": [1, 2, 3]}

    path = mfiles.write_data(data, base, dev_mode=False)

    assert path == base.with_suffix(".msgpack")
    assert path.exists()
    assert mfiles.read_data(base, dev_mode=False) == data


def test_write_and_read_data_roundtrip_yaml(tmp_path):
    base = tmp_path / "result" / "data"
    data = {"metadata": {"gameVersion": "16.3"}, "items": [1, 2, 3]}

    path = mfiles.write_data(data, base, dev_mode=True)

    assert path == base.with_suffix(".yml")
    assert path.exists()
    assert mfiles.read_data(base, dev_mode=True) == data


def test_get_game_version_success(tmp_path):
    game_path = tmp_path / "game"
    meta_file = game_path / "Game" / "content-metadata.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps({"version": "16.3.123.456"}), encoding="utf-8")

    assert game_version.get_game_version(game_path) == "16.3"


def test_get_game_version_invalid_version(tmp_path):
    game_path = tmp_path / "game"
    meta_file = game_path / "Game" / "content-metadata.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps({"version": "invalid"}), encoding="utf-8")

    with pytest.raises(ValueError):
        game_version.get_game_version(game_path)


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

    assert game_version.get_lcu_version(game_path) == "16.5"


def test_resolve_game_version_uses_remote_snapshot_version():
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

    assert game_version.resolve_game_version(ctx) == "16.5"
    assert ctx.runtime_cache["resolved_runtime_version"] == "16.5"


def test_build_metadata_payload():
    result = mutils.build_metadata_payload("16.3", ["default", "zh_CN"])

    metadata = result["metadata"]
    assert metadata["gameVersion"] == "16.3"
    assert metadata["scriptName"] == "lol-audio-unpack"
    assert metadata["languages"] == ["default", "zh_CN"]
    assert "scriptVersion" in metadata
    assert "createdAt" in metadata


def test_build_metadata_payload_prefers_injected_build_version(monkeypatch):
    monkeypatch.setenv("LOL_AUDIO_UNPACK_BUILD_VERSION", "3.7.1.dev14+gabc123")

    result = mutils.build_metadata_payload("16.12", ["zh_CN"])

    assert result["metadata"]["scriptVersion"] == "3.7.1.dev14+gabc123"


def test_build_metadata_payload_does_not_warn_when_injected_version_exists(monkeypatch):
    warnings: list[str] = []
    monkeypatch.setenv("LOL_AUDIO_UNPACK_BUILD_VERSION", "3.7.1")
    monkeypatch.setattr(
        mutils,
        "get_package_version",
        lambda _name: (_ for _ in ()).throw(mutils.PackageNotFoundError()),
    )
    monkeypatch.setattr(mutils.logger, "warning", warnings.append)

    result = mutils.build_metadata_payload("16.12", ["zh_CN"])

    assert result["metadata"]["scriptVersion"] == "3.7.1"
    assert warnings == []


def test_needs_update_behavior(tmp_path):
    base = tmp_path / "manifest" / "data"
    base.parent.mkdir(parents=True, exist_ok=True)

    # 文件不存在时需要更新
    assert mfiles.needs_update(base, "16.3", force_update=False, dev_mode=False) is True

    # 版本一致时不需要更新
    mfiles.write_data({"metadata": {"gameVersion": "16.3"}}, base, dev_mode=False)
    assert mfiles.needs_update(base, "16.3", force_update=False, dev_mode=False) is False

    # 版本不一致时需要更新
    assert mfiles.needs_update(base, "16.4", force_update=False, dev_mode=False) is True

    # 强制更新始终为True
    assert mfiles.needs_update(base, "16.3", force_update=True, dev_mode=False) is True


def test_read_data_logs_error_with_exception_when_loader_fails(tmp_path, monkeypatch):
    base = tmp_path / "broken"
    actual_file = base.with_suffix(".json")
    actual_file.write_text("{}", encoding="utf-8")

    opt_calls: list[dict[str, object]] = []
    errors: list[str] = []

    monkeypatch.setattr(mfiles, "find_data_file", lambda _path, dev_mode=False: actual_file)
    monkeypatch.setattr(mfiles, "load_json", lambda _path: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        mfiles,
        "logger",
        SimpleNamespace(
            trace=lambda _message: None,
            debug=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=errors.append),
        ),
    )

    result = mfiles.read_data(base, dev_mode=False)

    assert result == {}
    assert opt_calls == [{"exception": True}]
    assert errors == [f"读取文件时出错: {actual_file}, 错误: boom"]


def test_read_data_can_defer_deserialization_logging_to_aggregate_boundary(tmp_path, monkeypatch) -> None:
    """完整扫描可关闭逐 artifact traceback，由上层统一记录摘要。"""
    base = tmp_path / "broken"
    actual_file = base.with_suffix(".json")
    actual_file.write_text("{}", encoding="utf-8")
    opt_calls: list[dict[str, object]] = []

    monkeypatch.setattr(mfiles, "find_data_file", lambda _path, dev_mode=False: actual_file)
    monkeypatch.setattr(mfiles, "load_json", lambda _path: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        mfiles,
        "logger",
        SimpleNamespace(
            trace=lambda _message: None,
            debug=lambda _message: None,
            opt=lambda **kwargs: opt_calls.append(kwargs) or SimpleNamespace(error=lambda _message: None),
        ),
    )

    result = mfiles.read_data(base, dev_mode=False, log_errors=False)

    assert result == {}
    assert opt_calls == []


def test_write_data_preserves_existing_file_when_serialize_fails(tmp_path, monkeypatch):
    base = tmp_path / "out" / "data"
    target = base.with_suffix(".msgpack")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-data")

    monkeypatch.setattr(mfiles, "dump_msgpack", lambda _data, _path: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(ArtifactWriteError) as raised:
        mfiles.write_data({"k": "v"}, base, dev_mode=False)

    assert raised.value.path == target
    assert raised.value.stage == "serialize"
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert target.read_bytes() == b"old-data"
    assert list(target.parent.iterdir()) == [target]


def test_write_data_removes_temp_when_first_write_fails(tmp_path, monkeypatch):
    base = tmp_path / "out" / "data"
    target = base.with_suffix(".msgpack")
    monkeypatch.setattr(mfiles, "dump_msgpack", lambda _data, _path: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(ArtifactWriteError, match="serialize"):
        mfiles.write_data({"k": "v"}, base, dev_mode=False)

    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_write_data_preserves_existing_file_when_fsync_fails(tmp_path, monkeypatch):
    base = tmp_path / "out" / "data"
    target = base.with_suffix(".msgpack")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-data")
    monkeypatch.setattr(mfiles.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(ArtifactWriteError) as raised:
        mfiles.write_data({"k": "v"}, base, dev_mode=False)

    assert raised.value.stage == "fsync"
    assert target.read_bytes() == b"old-data"
    assert list(target.parent.iterdir()) == [target]


def test_write_data_preserves_existing_file_when_replace_fails(tmp_path, monkeypatch):
    base = tmp_path / "out" / "data"
    target = base.with_suffix(".msgpack")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-data")
    monkeypatch.setattr(mfiles.os, "replace", lambda _source, _target: (_ for _ in ()).throw(OSError("busy")))

    with pytest.raises(ArtifactWriteError) as raised:
        mfiles.write_data({"k": "v"}, base, dev_mode=False)

    assert raised.value.stage == "replace"
    assert target.read_bytes() == b"old-data"
    assert list(target.parent.iterdir()) == [target]


def test_copy_file_atomic_preserves_existing_file_when_copy_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.msgpack"
    target = tmp_path / "manifest" / "data.msgpack"
    source.write_bytes(b"new-data")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-data")
    monkeypatch.setattr(mfiles.shutil, "copy2", lambda _source, _target: (_ for _ in ()).throw(OSError("full")))

    with pytest.raises(ArtifactWriteError) as raised:
        mfiles.copy_file_atomic(source, target)

    assert raised.value.stage == "copy"
    assert target.read_bytes() == b"old-data"
    assert list(target.parent.iterdir()) == [target]


def test_copy_file_atomic_replaces_target_after_complete_copy(tmp_path):
    source = tmp_path / "source.msgpack"
    target = tmp_path / "manifest" / "data.msgpack"
    source.write_bytes(b"new-data")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-data")

    path = mfiles.copy_file_atomic(source, target)

    assert path == target
    assert target.read_bytes() == b"new-data"
    assert source.read_bytes() == b"new-data"
    assert list(target.parent.iterdir()) == [target]


def test_manager_utils_keeps_legacy_exports_for_files_and_game_version() -> None:
    assert mutils.find_data_file is mfiles.find_data_file
    assert mutils.read_data is mfiles.read_data
    assert mutils.write_data is mfiles.write_data
    assert mutils.needs_update is mfiles.needs_update
    assert mutils.get_game_version is game_version.get_game_version
    assert mutils.get_lcu_version is game_version.get_lcu_version
    assert mutils.resolve_context_version is game_version.resolve_game_version
    assert mutils.create_metadata_object is mutils.build_metadata_payload
    assert mutils.validate_local_version is game_version.validate_install_version
