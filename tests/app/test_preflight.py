"""验证所选源的存在性复查、精确范围和写入前失败。"""

from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.preflight import SourcePreflightError, check_source_files
from lol_audio_unpack.app.results import ResultStatus
from lol_audio_unpack.app.types import OperationOptions
from lol_audio_unpack.manager import source_inventory

pytestmark = pytest.mark.unit


@pytest.fixture
def source(monkeypatch, tmp_path):
    """仅隔离 LCU 解码；必需 GAME 文件由实际文件系统检查。"""
    champions = [{"id": 1, "alias": "Annie"}, {"id": 2, "alias": "Olaf"}]
    metadata = {"globalAssetBundles": ["default.wad"], "perLocaleAssetBundles": {"ja_JP": ["japanese.wad"]}}
    monkeypatch.setattr(source_inventory, "read_catalog", lambda _: (champions, [{"id": 0}, {"id": 11}], metadata))
    for bundle in ("default.wad", "japanese.wad"):
        path = tmp_path / source_inventory.LCU_ROOT / bundle
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    for stem in ("Champions/Annie", "Maps/Shipping/Common", "Maps/Shipping/Map11"):
        for suffix in (".wad.client", ".ja_JP.wad.client"):
            path = tmp_path / source_inventory.FINAL_ROOT / (stem + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not a valid WAD, existence alone is sufficient")
    return SimpleNamespace(
        config=SimpleNamespace(game_path=tmp_path, game_region="ja_JP"),
        game_region="ja_JP",
        runtime_cache={},
    )


def test_scope_is_not_reduced_and_file_is_rechecked_after_selection(source):
    """单英雄可用不被无关英雄阻止，全部范围缺失则失败，删文件后复核失败。"""
    check_source_files(source, champion_ids=("Annie",))
    with pytest.raises(SourcePreflightError, match="champion:2"):
        check_source_files(source)
    path = source.config.game_path / source_inventory.FINAL_ROOT / "Champions/Annie.ja_JP.wad.client"
    path.unlink()
    with pytest.raises(SourcePreflightError) as error:
        check_source_files(source, champion_ids=(1,))
    assert error.value.missing == ("Game/DATA/FINAL/Champions/Annie.ja_JP.wad.client",)


def test_map_requires_common_and_unknown_selection_is_rejected(source):
    """显式地图同样需要 Common，不把未知 ID 解释成空成功。"""
    check_source_files(source, map_ids=(11,))
    with pytest.raises(SourcePreflightError, match="未知实体"):
        check_source_files(source, champion_ids=(999,))
    (source.config.game_path / source_inventory.FINAL_ROOT / "Maps/Shipping/Common.ja_JP.wad.client").unlink()
    with pytest.raises(SourcePreflightError) as error:
        check_source_files(source, map_ids=(11,))
    assert {entity.key for entity in error.value.entities} == {"0", "11"}


def test_facade_missing_source_fails_before_metadata_writes(source, monkeypatch):
    """门面必须在准备元数据之前阻止缺失范围，不能仅靠 GUI 禁选。"""
    app = LolAudioUnpackApp(source)
    writes = []
    monkeypatch.setattr(app, "prepare_update_data", lambda **_: writes.append("metadata"))
    result = app.update(OperationOptions(champion_ids=(2,)))
    assert result.status is ResultStatus.FAILED
    assert result.error_type == "SourcePreflightError"
    assert writes == []


def test_explicit_resource_pack_does_not_require_ordinary_voice(source):
    """资源包按显式物理输入检查，不套用普通英雄本地化命名规则。"""
    relative = "Game/DATA/FINAL/Champions/Annie.wad.client"
    check_source_files(source, resource_only=True, resource_wads=(relative,))
    source.game_region = ""
    with pytest.raises(SourcePreflightError, match="请选择"):
        check_source_files(source, resource_only=True, resource_wads=(relative,))
