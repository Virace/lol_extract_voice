import json

import pytest

from lol_audio_unpack.Data.Manifest import GameDataReader, compare_version, is_valid_version
from lol_audio_unpack.utils.common import Singleton


@pytest.fixture(autouse=True)
def reset_game_data_reader_singleton():
    Singleton._instances.pop(GameDataReader, None)
    yield
    Singleton._instances.pop(GameDataReader, None)


def test_is_valid_version():
    assert is_valid_version("15.14")
    assert is_valid_version("15.14.1")
    assert not is_valid_version("15")
    assert not is_valid_version("a.b")
    assert not is_valid_version("15.14.1.2")


def test_compare_version_major_mismatch_raises():
    with pytest.raises(ValueError, match="大版本不同"):
        compare_version("14.10", "15.1")


def test_compare_version_minor_mismatch_no_raise():
    compare_version("15.10", "15.11")


def test_game_data_reader_basic_lookup(tmp_path):
    data = {
        "gameVersion": "15.14",
        "indices": {"alias": {"ahri": "103"}},
        "champions": {
            "103": {
                "id": 103,
                "alias": "Ahri",
                "names": {"default": "Ahri", "zh_CN": "阿狸"},
            }
        },
    }
    data_file = tmp_path / "merged_data.json"
    data_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    reader = GameDataReader(data_file)
    assert reader.version == "15.14"
    assert reader.get_champion_by_id(103)["alias"] == "Ahri"
    assert reader.get_champion_by_alias("ahri")["id"] == 103
    assert reader.get_champions_list()[0]["id"] == 103

    languages = set(reader.get_supported_languages())
    assert {"default", "zh_CN"}.issubset(languages)
