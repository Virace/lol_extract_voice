from lol_audio_unpack.utils.common import (
    capitalize_first_letter,
    de_duplication,
    format_region,
    list2dict,
    re_replace,
    replace,
    str_get_number,
)


def test_capitalize_first_letter_basic_cases():
    assert capitalize_first_letter("ahri") == "Ahri"
    assert capitalize_first_letter("") == ""


def test_str_get_number_short_and_long_input():
    assert str_get_number("skin_62007") == 62007

    long_text = "x" * 1200 + "id=777"
    assert str_get_number(long_text, threshold=1000) == 777


def test_format_region():
    assert format_region("zh_cn") == "zh_CN"
    assert format_region("default") == "default"


def test_de_duplication():
    base = {"a", "b"}
    items = [("a", "b"), ("b", "c"), ("d", "e")]
    merged, deduped = de_duplication(base, items)

    assert merged == {"a", "b", "c", "d", "e"}
    assert deduped == {("b", "c"), ("d", "e")}


def test_replace_and_re_replace():
    text = "Hello, Ahri"
    assert replace(text, {"Hello": "Hi"}) == "Hi, Ahri"

    replaced = re_replace("skin12", {r"skin(\d+)": "Skin-{}"})
    assert replaced == "Skin-12"


def test_list2dict():
    data = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    assert list2dict(data, "id") == {1: {"id": 1, "name": "A"}, 2: {"id": 2, "name": "B"}}
