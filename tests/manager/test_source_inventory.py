"""验证本地文件快照保留完整名单、共享依赖与英语独立文件要求。"""

from pathlib import Path

import pytest

from lol_audio_unpack.manager import source_inventory as inventory

pytestmark = pytest.mark.unit
ENTITY_COUNT = 4
MAP_COUNT = 2
GENERATION = 8


@pytest.fixture
def local_catalog(monkeypatch, tmp_path):
    """隔离 LCU 解码边界，提供包含共享英雄和 Common 的完整目录。"""
    champions = [{"id": 62, "alias": "MonkeyKing"}, {"id": 60062, "alias": "Jade_Wukong"}]
    maps = [{"id": 0}, {"id": 11}]
    metadata = {"globalAssetBundles": ["default-assets.wad"], "perLocaleAssetBundles": {"ja_JP": ["ja_JP-assets.wad"]}}
    monkeypatch.setattr(inventory, "read_catalog", lambda _: (champions, maps, metadata))
    for filename in ("default-assets.wad", "ja_JP-assets.wad"):
        path = tmp_path / inventory.LCU_ROOT / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    for relative in ("Champions/MonkeyKing", "Maps/Shipping/Common", "Maps/Shipping/Map11"):
        for suffix in (".wad.client", ".ja_JP.wad.client"):
            path = tmp_path / inventory.FINAL_ROOT / f"{relative}{suffix}"
            path.parent.mkdir(parents=True, exist_ok=True)
            # 存在性检查必须接受损坏内容，实际解析仍归运行阶段负责。
            path.write_bytes(b"invalid wad bytes")
    return tmp_path


def test_only_japanese_is_available_without_english_wads(local_catalog):
    """default LCU 不是 GAME 英语语音存在的证据。"""
    snapshot = inventory.scan_inventory(local_catalog, generation=GENERATION)
    japanese = snapshot.get_language("ja_JP")
    assert snapshot.generation == GENERATION
    assert japanese.status == "complete"
    assert japanese.available_count == ENTITY_COUNT
    assert snapshot.get_language("en_US").status == "unavailable"
    jade = next(entity for entity in japanese.entities if entity.key == "60062")
    assert "Game/DATA/FINAL/Champions/MonkeyKing.ja_JP.wad.client" in jade.required
    assert all(not Path(path).is_absolute() for path in jade.required)


def test_missing_shared_file_keeps_all_entities_and_deduplicates(local_catalog):
    """一个共享物理文件影响多个实体，缺失文件数不等于受影响实体数。"""
    path = local_catalog / inventory.FINAL_ROOT / "Champions/MonkeyKing.ja_JP.wad.client"
    path.unlink()
    japanese = inventory.scan_inventory(local_catalog).get_language("ja_JP")
    assert japanese.status == "partial"
    assert len(japanese.entities) == ENTITY_COUNT
    assert japanese.available_count == MAP_COUNT
    assert japanese.missing == ("Game/DATA/FINAL/Champions/MonkeyKing.ja_JP.wad.client",)
    assert {entity.key for entity in japanese.entities if not entity.available} == {"62", "60062"}
    path.touch()
    assert inventory.scan_inventory(local_catalog).get_language("ja_JP").status == "complete"
    assert japanese.status == "partial"


def test_common_dependency_blocks_maps_and_lcu_dependency_blocks_language(local_catalog):
    """地图依赖 Common，本地化大厅 bundle 缺失时不能回退 default。"""
    (local_catalog / inventory.FINAL_ROOT / "Maps/Shipping/Common.wad.client").unlink()
    japanese = inventory.scan_inventory(local_catalog).get_language("ja_JP")
    assert {entity.key for entity in japanese.entities if not entity.available} == {"0", "11"}
    (local_catalog / inventory.LCU_ROOT / "ja_JP-assets.wad").unlink()
    japanese = inventory.scan_inventory(local_catalog).get_language("ja_JP")
    assert japanese.status == "unavailable"
    assert len(japanese.entities) == ENTITY_COUNT


def test_discovery_failure_is_not_an_empty_complete_snapshot(tmp_path):
    """无法取得完整目录必须失败，不能声称零缺失。"""
    with pytest.raises(inventory.SourceDiscoveryError):
        inventory.scan_inventory(tmp_path)


def test_historical_structured_mode_does_not_invent_localized_wads(monkeypatch, local_catalog):
    """旧结构化模式沿用基础 WAD 声明，不借普通英雄模板增加未知依赖。"""
    champions, maps, metadata = inventory.read_catalog(local_catalog)
    champions.append({"id": 66600, "alias": "Ruby_Urgot"})
    path = local_catalog / inventory.FINAL_ROOT / "Champions/Ruby_Urgot.wad.client"
    path.touch()
    monkeypatch.setattr(inventory, "read_catalog", lambda _: (champions, maps, metadata))
    japanese = inventory.scan_inventory(local_catalog).get_language("ja_JP")
    special = next(entity for entity in japanese.entities if entity.key == "66600")
    assert special.available
    assert special.required[-1] == "Game/DATA/FINAL/Champions/Ruby_Urgot.wad.client"
