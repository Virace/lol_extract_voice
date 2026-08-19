"""resource binding schema 与路径合同测试。"""

from __future__ import annotations

import pytest

from lol_audio_unpack.model.binding import (
    RESOURCE_SCHEMA_VERSION,
    BankBinding,
    BinBinding,
    BindingRole,
    BindingStatus,
    Completeness,
    ResourceBindings,
    build_diagnostics,
    normalize_logical_path,
)

pytestmark = pytest.mark.unit


def test_resource_bindings_round_trip_preserves_schema_and_partial_diagnostics() -> None:
    """v2 artifact 应保留固定字段并从 bindings 派生 partial。"""
    bins = [
        BinBinding(
            path=r"DATA\Characters\Jade_Fiddlesticks\Skins\Skin301.bin",
            normalized_path="",
            wad="Game/DATA/FINAL/Champions/FiddleSticks.wad.client",
            entry_hash="0000000000000001",
            status=BindingStatus.RESOLVED,
            role=BindingRole.ROOT,
        )
    ]
    banks = [
        BankBinding(
            category="Characters/Jade_Fiddlesticks/Skins/Skin301/VO",
            path="assets/sounds/wwise2016/vo/jade_audio.bnk",
            normalized_path="",
            kind="bnk",
            wad="Game/DATA/FINAL/Champions/FiddleSticks.zh_CN.wad.client",
            entry_hash="0000000000000002",
            source_bin=bins[0].path,
            role=BindingRole.LOCALIZED,
            status=BindingStatus.RESOLVED,
            sub_entity="301",
            group=0,
        ),
        BankBinding(
            category="Characters/Jade_Fiddlesticks/Skins/Skin301/SFX",
            path="assets/sounds/wwise2016/sfx/missing_audio.bnk",
            normalized_path="",
            kind="BNK",
            wad=None,
            entry_hash="0000000000000003",
            source_bin=bins[0].path,
            role=None,
            status=BindingStatus.MISSING,
            sub_entity="301",
            group=1,
        ),
    ]
    bindings = ResourceBindings(
        entity_type="champion",
        entity_id="60009",
        bin_bindings=tuple(bins),
        bank_bindings=tuple(banks),
        diagnostics=build_diagnostics(bins, banks),
    )

    payload = bindings.to_payload(skins={"301": {}})
    restored = ResourceBindings.from_payload(payload)

    assert payload["resourceSchemaVersion"] == RESOURCE_SCHEMA_VERSION
    assert payload["entity"] == {"type": "champion", "id": "60009"}
    assert payload["binBindings"][0]["normalizedPath"] == ("data/characters/jade_fiddlesticks/skins/skin301.bin")
    assert payload["bankBindings"][0]["sourceBin"] == ("data/characters/jade_fiddlesticks/skins/skin301.bin")
    assert payload["diagnostics"]["completeness"] == "partial"
    assert payload["skins"] == {"301": {}}
    assert restored == bindings


def test_binding_without_resolved_bank_is_failed() -> None:
    """只有 BIN 成功而没有可消费 bank 时应标记 failed。"""
    bins = [
        BinBinding(
            path="data/test.bin",
            normalized_path="",
            wad="Game/DATA/FINAL/Test.wad.client",
            entry_hash="0000000000000001",
            status=BindingStatus.RESOLVED,
        )
    ]

    assert build_diagnostics(bins, []).completeness is Completeness.FAILED


@pytest.mark.parametrize(
    "wad",
    [
        r"C:\Games\League\Game\Test.wad.client",
        "C:Game/Test.wad.client",
        "/Game/Test.wad.client",
        "../Test.wad.client",
    ],
)
def test_binding_rejects_absolute_or_escaping_wad_identity(wad: str) -> None:
    """artifact 不得持久化绝对或逃逸游戏根的 WAD 路径。"""
    with pytest.raises(ValueError, match="WAD identity"):
        BinBinding(
            path="data/test.bin",
            normalized_path="",
            wad=wad,
            entry_hash="0000000000000001",
            status=BindingStatus.RESOLVED,
        )


def test_normalize_logical_path_unifies_slashes_prefix_and_case() -> None:
    """逻辑路径比较必须统一斜杠、前导分隔符和大小写。"""
    assert normalize_logical_path(r"\DATA\\Characters\Annie\skin.bin") == "data/characters/annie/skin.bin"


def test_resource_bindings_rejects_legacy_payload() -> None:
    """require 边界不得把旧 local banks 当作 v2。"""
    with pytest.raises(ValueError, match="重新运行 update"):
        ResourceBindings.from_payload({"championId": "1", "skins": {}})


def test_bank_binding_semantic_key_can_keep_multiple_physical_entries() -> None:
    """同一 category/path 的多个物理 entry 不得被 dict 覆盖。"""
    banks = [
        BankBinding(
            category="Shared_SFX",
            path="assets/shared_audio.bnk",
            normalized_path="",
            kind="BNK",
            wad=wad,
            entry_hash=f"{index:016x}",
            source_bin="data/shared.bin",
            role=BindingRole.ROOT,
            status=BindingStatus.RESOLVED,
        )
        for index, wad in enumerate(
            ["Game/DATA/FINAL/A.wad.client", "Game/DATA/FINAL/B.wad.client"],
            start=1,
        )
    ]
    bindings = ResourceBindings(
        entity_type="map",
        entity_id="22",
        bin_bindings=(),
        bank_bindings=tuple(banks),
        diagnostics=build_diagnostics([], banks),
    )

    payload = bindings.to_payload()

    assert [item["wad"] for item in payload["bankBindings"]] == [
        "Game/DATA/FINAL/A.wad.client",
        "Game/DATA/FINAL/B.wad.client",
    ]
