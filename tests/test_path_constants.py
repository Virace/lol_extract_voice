import pytest

from lol_audio_unpack.utils import path_constants as pc


pytestmark = pytest.mark.unit


def test_get_output_dir_name():
    assert pc.get_output_dir_name("champion") == "champions"
    assert pc.get_output_dir_name("map") == "maps"


def test_get_output_dir_name_invalid():
    with pytest.raises(ValueError):
        pc.get_output_dir_name("unknown")


def test_get_game_dir_name():
    assert pc.get_game_dir_name("champion") == "Champions"
    assert pc.get_game_dir_name("map") == "Maps"


def test_get_game_dir_name_invalid():
    with pytest.raises(ValueError):
        pc.get_game_dir_name("unknown")


def test_format_entity_folder_name():
    assert pc.format_entity_folder_name("1", "annie", "安妮") == "1·annie·安妮"
    assert pc.format_entity_folder_name("1", "annie", "安妮", "黑暗之女") == "1·annie·安妮·黑暗之女"


def test_format_sub_entity_folder_name():
    assert pc.format_sub_entity_folder_name("1001", "默认皮肤") == "1001·默认皮肤"
