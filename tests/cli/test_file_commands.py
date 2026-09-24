"""独立命令的实体定位、JSON 管道与文件清单契约。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import msgpack
import pytest

from lol_audio_unpack.cli.cli import main
from lol_audio_unpack.runtime.wav.files import build_scopes, read_inputs

pytestmark = pytest.mark.unit
EXIT_INPUT = 2


def test_export_json_selects_entity_without_game_context(tmp_path, monkeypatch, capsys):
    """公开入口仅按指定实体读取完整映射，stdout 可以直接解析为 JSON。"""
    root = tmp_path / "output"
    path = root / "hashes/16.19/zh_CN/integrated/maps/0.msgpack"
    path.parent.mkdir(parents=True)
    payload = {"mapId": 0, "name": "常规", "events": {"Play_sfx_3084_hit": [30036669, 112272935]}}
    path.write_bytes(msgpack.packb(payload, use_bin_type=True))
    original = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["unpack", "export-json", "--maps", "0"])

    assert main() == 0
    assert json.loads(capsys.readouterr().out) == payload
    assert path.read_bytes() == original
    assert not (root / "logs").exists()


def test_export_json_requires_version_when_ambiguous(tmp_path, monkeypatch, capsys):
    """同时存在两版相同实体时必须显式选择，不能按修改时间猜版本。"""
    for version in ("16.18", "16.19"):
        path = tmp_path / f"hashes/{version}/zh_CN/champions/1.msgpack"
        path.parent.mkdir(parents=True)
        path.write_bytes(msgpack.packb({"metadata": {"gameVersion": version}, "championId": 1}))
    argv = ["unpack", "export-json", "--champions", "1", "--output-path", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", argv)
    assert main() == EXIT_INPUT
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(sys, "argv", [*argv, "--game-version", "16.18"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["metadata"]["gameVersion"] == "16.18"


def test_input_list_resolves_relative_files_without_merging_same_id(tmp_path):
    """清单相对路径、BOM、空格和重复引用不丢失同 ID 的不同文件。"""
    root = tmp_path / "音频 清单"
    paths = [root / "base/42.wem", root / "skin/42.wem"]
    for path in paths:
        path.parent.mkdir(parents=True)
        path.write_bytes(b"only path selection is tested")
    listing = root / "selected.txt"
    listing.write_text('\n"base/42.wem"\n\nskin/42.wem\nbase/42.wem\n', encoding="utf-8-sig")

    sources = read_inputs([paths[0]], listing)
    scopes = build_scopes(sources)
    assert sources == tuple(path.resolve() for path in paths)
    assert len(scopes) == 1
    assert scopes[0].root == root.resolve()
    assert scopes[0].files == ("base/42.wem", "skin/42.wem")
    assert scopes[0].resolve_files() == sources


@pytest.mark.parametrize("extra", [["extract"], ["--wav-workers", "0"], ["--input", "missing.wem"]])
def test_convert_wem_rejects_invalid_input_before_output(tmp_path, monkeypatch, extra):
    """组合动作、非法并发和缺失文件都不能触发游戏初始化或创建输出。"""
    target = tmp_path / "wavs"
    monkeypatch.setattr(sys, "argv", ["unpack", "convert-wem", "--output-path", str(target), *extra])
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code
    assert code == EXIT_INPUT
    assert not target.exists()
