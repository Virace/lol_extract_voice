import json
from pathlib import Path

import pytest

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
