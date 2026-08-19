"""验证总览预览从路径级音频引用恢复真实目录。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.service.data_loader import EntityDataLoader


def _build_loader(*, group_by_type: bool) -> EntityDataLoader:
    """构造仅用于音频根目录推导的最小数据加载器。"""
    loader = EntityDataLoader.__new__(EntityDataLoader)
    loader.ctx = SimpleNamespace(config=SimpleNamespace(group_by_type=group_by_type))
    return loader


def _make_ref(relative_path: str, path: Path) -> AudioRef:
    """构造音频根目录测试所需的最小路径级引用。"""
    return AudioRef(
        relative_path=relative_path,
        path=path,
        wem_id=path.stem,
        audio_type="VO",
        sub_entity="1000",
    )


def test_load_audio_roots_ungrouped_champion_and_lobby_share_entity_root(tmp_path: Path) -> None:
    """非分类型输出下，角色与 lobby WEM 应去重到同一实体目录。"""
    loader = _build_loader(group_by_type=False)
    entity_root = tmp_path / "audios" / "16.16" / "champions" / "1-annie"
    refs = (
        _make_ref("1000/VO/1001.wem", entity_root / "1000" / "VO" / "1001.wem"),
        _make_ref("lobby/1002.wem", entity_root / "lobby" / "1002.wem"),
    )

    roots = loader.load_audio_roots("champions", "1", audio_refs=refs)

    assert roots == (entity_root,)


def test_load_audio_roots_grouped_keeps_type_and_lobby_roots_in_stable_order(tmp_path: Path) -> None:
    """分类型输出应保留 VO、SFX 与 lobby 的独立真实根目录。"""
    loader = _build_loader(group_by_type=True)
    version_root = tmp_path / "audios" / "16.16"
    entity_root = version_root / "champions" / "1-annie"
    vo_root = version_root / "VO" / "champions" / "1-annie"
    sfx_root = version_root / "SFX" / "champions" / "1-annie"
    lobby_root = entity_root / "lobby"
    refs = (
        _make_ref("VO/1000/1001.wem", vo_root / "1000" / "1001.wem"),
        _make_ref("SFX/1000/1002.wem", sfx_root / "1000" / "1002.wem"),
        _make_ref("lobby/1003.wem", lobby_root / "1003.wem"),
    )

    roots = loader.load_audio_roots("champions", "1", audio_refs=refs)

    assert roots == tuple(sorted((vo_root, sfx_root, lobby_root), key=lambda path: str(path).casefold()))
