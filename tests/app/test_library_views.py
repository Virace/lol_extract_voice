"""新库语言隔离、搬迁读取与旧元数据只读边界。"""

import shutil
from dataclasses import replace

import pytest

from lol_audio_unpack.app.artifacts import enumerate_audio_refs
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.manager.errors import SharedDataMissingError
from lol_audio_unpack.manager.files import write_data
from lol_audio_unpack.model import AudioEntityData
from tests.factories import make_context, make_library_view

pytestmark = pytest.mark.integration


def test_region_switch_and_library_move_preserve_exact_media(tmp_path):
    """同版本同 ID 的两种语言独立读取，搬迁无需改索引中的路径。"""
    root = tmp_path / "library"
    ctx = make_context(root)
    entity = AudioEntityData(
        "1", "安妮", "Annie", None, "champion", {"1000": {"name": "基础", "categories": {}}}, "Game/a.wad.client"
    )
    for region in ("zh_CN", "ja_JP"):
        ctx.config = replace(ctx.config, game_region=region)
        make_library_view(ctx, entity, "16.18", data=region.encode())
    ctx.config = replace(ctx.config, game_region="zh_CN")
    chinese = enumerate_audio_refs(ctx, entity, "16.18")
    ctx.config = replace(ctx.config, game_region="ja_JP")
    japanese = enumerate_audio_refs(ctx, entity, "16.18")
    assert chinese[0].wem_id == japanese[0].wem_id == "101"
    assert chinese[0].path.read_bytes() == b"zh_CN" and japanese[0].path.read_bytes() == b"ja_JP"
    moved = tmp_path / "moved"
    shutil.copytree(root, moved)
    new_ctx = make_context(moved, game_region="ja_JP")
    (restored,) = enumerate_audio_refs(new_ctx, entity, "16.18")
    assert restored.path.is_relative_to(moved) and restored.path.read_bytes() == b"ja_JP"
    assert restored.relative_path == japanese[0].relative_path


def test_old_metadata_never_becomes_a_runtime_catalog(tmp_path):
    """未经过入口迁移的旧布局不能成为运行时读取回退。"""
    ctx = make_context(tmp_path, runtime_cache={"resolved_runtime_version": "16.18"})
    old = ctx.paths.manifest_path / "16.18/data"
    write_data({"metadata": {"gameVersion": "16.18"}, "champions": {}, "maps": {}}, old)
    before = old.with_suffix(".msgpack").read_bytes()
    for read_only in (False, True):
        with pytest.raises(SharedDataMissingError):
            DataReader(ctx, read_only=read_only)
    assert old.with_suffix(".msgpack").read_bytes() == before
