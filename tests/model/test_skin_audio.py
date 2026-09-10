"""皮肤共享归属与差异边界的行为测试。"""

from dataclasses import replace

from lol_audio_unpack.model import AudioBank
from lol_audio_unpack.model.binding import BankBinding, BindingRole, BindingStatus
from lol_audio_unpack.model.skin_audio import SkinAudio


def make_bank(skin: str, entry: str, *, category: str = "Hero_Base_VO") -> AudioBank:
    """构造有明确物理身份的皮肤声明。"""
    return AudioBank(
        sub_id=skin,
        audio_type="VO",
        binding=BankBinding(
            category=category,
            path=f"assets/{entry}_audio.bnk",
            normalized_path="",
            kind="BNK",
            wad="Game/hero.wad.client",
            entry_hash=entry,
            source_bin=f"data/skin{skin}.bin",
            role=BindingRole.ROOT,
            status=BindingStatus.RESOLVED,
            sub_entity=skin,
        ),
    )


def test_shared_banks_keep_parent_ownership_and_chroma_additions() -> None:
    """即使输入反序、父级 ID 更大，纯共享不复制，混合炫彩只多一个独立容器。"""
    banks = (
        make_bank("3", "a"),
        make_bank("3", "b"),
        make_bank("3", "c"),
        make_bank("2", "a"),
        make_bank("2", "b"),
        make_bank("9", "a"),
        make_bank("1", "a"),
    )
    parents = {"9": None, "1": "9", "2": "9", "3": "2"}
    for declared in (banks, tuple(reversed(banks))):
        audio = SkinAudio(declared, parents)
        assert {(bank.sub_id, bank.binding.entry_hash) for bank in audio.output_banks()} == {
            ("9", "a"),
            ("2", "b"),
            ("3", "c"),
        }
        assert audio.is_shared(("1", "Hero_Base_VO"))
        assert not audio.is_shared(("3", "Hero_Base_VO"))
        assert set(audio.sources(("3", "Hero_Base_VO"))) == {("9", "Hero_Base_VO"), ("2", "Hero_Base_VO")}
        assert audio.shared_payload()["3"]["Hero_Base_VO"]["status"] == "mixed"
    assert banks[0].binding.sub_entity == "3"


def test_unresolved_or_different_sources_are_not_dropped_as_shared() -> None:
    """同名不同 WAD、未解析声明、不同类型都保留，不能只凭名称或 hash 合并。"""
    base = make_bank("1", "a")
    same = make_bank("2", "a")
    unresolved = replace(same, binding=replace(same.binding, status=BindingStatus.MISSING))
    other = replace(same, binding=replace(same.binding, wad="Game/other.wad.client"))
    sfx = replace(same, audio_type="SFX", binding=replace(same.binding, category="Hero_Base_SFX"))
    audio = SkinAudio((base, same, unresolved, other, sfx), {"1": None, "2": "1"})

    expected = (base, unresolved, other, sfx)
    assert len(audio.output_banks()) == len(expected)
    assert all(bank in audio.output_banks() for bank in expected)
    assert not audio.is_shared(("2", "Hero_Base_VO"))
    assert not audio.is_complete(("2", "Hero_Base_VO"))
    assert audio.owner(unresolved) is unresolved
    assert audio.owner(other) is other
    assert audio.owner(sfx) is sfx


def test_mapping_keeps_complete_changed_events_and_distinct_files_with_same_id() -> None:
    """纯继承事件不重复展开；变化事件保留共享引用及同 ID 的独立文件。"""
    banks = (make_bank("1", "a"), make_bank("2", "a"), make_bank("3", "a"), make_bank("3", "b"))
    audio = SkinAudio(banks, {"1": None, "2": "1", "3": "1"})
    category = "Hero_Base_VO"
    base_path = "1/VO/10.wem"
    skins = {
        "1": {"events": {category: {"old": [10]}}, "audioPaths": {category: {"old": [base_path]}}},
        "2": {
            "events": {category: {"old": [10], "new": [10]}},
            "audioPaths": {category: {"old": [base_path], "new": [base_path]}},
        },
        "3": {
            "events": {category: {"old": [10, 11, 12]}},
            "audioPaths": {category: {"old": [base_path, "3/VO/10.wem", "3/VO/11.wem"]}},
        },
    }
    projected = audio.mapping_differences(skins)

    assert projected["2"]["events"][category] == {"new": [10]}
    assert projected["2"]["audioPaths"][category] == {"new": [base_path]}
    assert projected["3"]["events"][category] == {"old": [10, 11, 12]}
    assert projected["3"]["audioPaths"][category]["old"] == [base_path, "3/VO/10.wem", "3/VO/11.wem"]
    assert "old" in skins["2"]["events"][category]

    skins["3"]["audioPaths"][category]["old"] = [base_path, "3/VO/11.wem"]
    assert audio.mapping_differences(skins)["3"]["events"][category] == {"old": [10, 11, 12]}


def test_same_category_and_event_keep_additions_from_another_bank() -> None:
    """同分类同事件从四条扩展为六条时，事件树保留完整六条并引用已有共享文件。"""
    category = "Hero_Base_VO"
    audio = SkinAudio(
        (make_bank("1000", "a"), make_bank("1013", "a"), make_bank("1013", "b")),
        {"1000": None, "1013": "1000"},
    )
    base_paths = [f"1000/VO/{value}.wem" for value in (1, 2, 3, 4)]
    added_paths = [f"1013/VO/{value}.wem" for value in (5, 6)]
    skins = {
        "1000": {"events": {category: {"play": [1, 2, 3, 4]}}, "audioPaths": {category: {"play": base_paths}}},
        "1013": {
            "events": {category: {"play": [1, 2, 3, 4, 5, 6]}},
            "audioPaths": {category: {"play": base_paths + added_paths}},
        },
    }

    projected = audio.mapping_differences(skins)

    assert projected["1013"]["events"][category] == {"play": [1, 2, 3, 4, 5, 6]}
    assert projected["1013"]["audioPaths"][category] == {"play": base_paths + added_paths}
    assert skins["1013"]["events"][category] == {"play": [1, 2, 3, 4, 5, 6]}
