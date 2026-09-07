"""验证单实体选择的路径身份、紧凑描述与撤销契约。"""

import json
from pathlib import Path

import pytest

from lol_audio_unpack.app.audio_scope import MappingNode
from lol_audio_unpack.app.audio_selection import AudioSelection

pytestmark = pytest.mark.unit
CATALOG_SIZE = 10000
PAIR_SIZE = 2


def test_selection_shares_paths_and_keeps_directory_exclusions(tmp_path: Path) -> None:
    """父节点与重复事件引用共享路径状态，全选取消一项仍提交目录加排除项。"""
    first = tmp_path / "base/1.wem"
    second = tmp_path / "skin/1.wem"
    missing = tmp_path / "missing.wem"
    selection = AudioSelection()
    selection.set_available((first, first, second))
    selection.set_paths((first, second, missing), True)
    assert selection.count == PAIR_SIZE
    assert not selection.contains(missing)
    selection.set_paths((first,), False)
    assert selection.contains(second)
    selection.undo()
    assert selection.count == PAIR_SIZE
    selection.select_all()
    selection.set_paths((first,), False)
    (scope,) = selection.build_scopes((tmp_path,))
    assert scope.directories == (".",)
    assert scope.files == ()
    assert scope.excluded == frozenset({"base/1.wem"})
    selection.clear()
    assert not selection.has_selection
    selection.undo()
    assert selection.count == 1
    selection.reset()
    assert not selection.has_selection and not selection.can_undo


def test_full_selection_is_compact_for_large_catalog(tmp_path: Path) -> None:
    """万级全选不在执行请求或撤销状态中复制整个文件清单。"""
    selection = AudioSelection()
    selection.set_available(tmp_path / f"{index}.wem" for index in range(CATALOG_SIZE))
    selection.select_all()
    (scope,) = selection.build_scopes((tmp_path,))
    assert scope.directories == (".",)
    assert scope.files == () and selection.state.included == frozenset()
    selection.set_paths((tmp_path / "5.wem",), False)
    assert selection.count == CATALOG_SIZE - 1
    selection.undo()
    assert selection.count == CATALOG_SIZE


@pytest.mark.parametrize("integrated", [False, True])
@pytest.mark.parametrize("prefix", ["", "VO"])
def test_node_scope_resolves_in_background_and_rejects_changed_mapping(
    tmp_path: Path, integrated: bool, prefix: str
) -> None:
    """分组和事件提交稳定引用，后台按精确路径解析，映射变更后拒绝静默扩大范围。"""
    root = tmp_path / "audios"
    root.mkdir()
    members = (root / "1.wem", root / "2.wem")
    for path in members:
        path.write_bytes(b"wem")
    paths = [f"{prefix}/{number}.wem" if prefix else f"{number}.wem" for number in (1, 2, 3)]
    events = {"VO": {"a": ["1", "2", "3"], "b": ["4"]}}
    audio_paths = {"VO": {"a": paths, "b": ["4.wem"]}}
    payload = (
        {"data": {"skins": [{"id": "1000", "events": {"VO": {"mapping": events["VO"]}}, "audioPaths": audio_paths}]}}
        if integrated
        else {"skins": {"1000": {"events": events, "audioPaths": audio_paths}}}
    )
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(payload))
    stat = mapping_path.stat()
    node = MappingNode(mapping_path, "champions", "1", (stat.st_size, stat.st_mtime_ns), ("1000", "VO", "a"))
    selection = AudioSelection()
    selection.set_available(members)
    selection.set_node(node, members, True)
    selection.set_paths((members[0],), False)
    (scope,) = selection.build_scopes((root,), prefixes={root: prefix})
    assert scope.files == () and scope.directories == () and len(scope.nodes) == 1
    assert scope.resolve_files() == (members[1],)
    selection.undo()
    (scope,) = selection.build_scopes((root,), prefixes={root: prefix})
    assert set(scope.resolve_files()) == set(members)
    mapping_path.write_text("{}")
    with pytest.raises(ValueError, match="映射已变化"):
        scope.resolve_files()
