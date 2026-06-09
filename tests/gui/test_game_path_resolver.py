"""GUI 游戏目录识别测试。"""

from __future__ import annotations

import json
from pathlib import Path

from lol_audio_unpack.gui.controllers.game_path_resolver import resolve_game_path


def _write_game_root(root: Path, *, version: str = "16.11.1234") -> Path:
    """写入最小可识别的现行客户端目录结构。"""

    game_dir = root / "Game"
    lcu_dir = root / "LeagueClient"
    plugin_dir = lcu_dir / "Plugins" / "rcp-be-lol-game-data"
    champions_dir = game_dir / "DATA" / "FINAL" / "Champions"
    maps_dir = game_dir / "DATA" / "FINAL" / "Maps" / "Shipping"

    for path in (game_dir, plugin_dir, champions_dir, maps_dir):
        path.mkdir(parents=True, exist_ok=True)

    (game_dir / "content-metadata.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (game_dir / "League of Legends.exe").write_bytes(b"")
    (lcu_dir / "LeagueClient.exe").write_bytes(b"")
    return root


def test_resolves_real_game_root(tmp_path: Path) -> None:
    """选择真实客户端根目录时应直接识别。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root)

    assert result.resolved is True
    assert result.root == root
    assert result.version == "16.11"
    assert result.reason == "resolved"


def test_resolves_game_subdirectory(tmp_path: Path) -> None:
    """选择 Game 目录时应回推到客户端根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "Game")

    assert result.resolved is True
    assert result.root == root


def test_resolves_league_client_subdirectory(tmp_path: Path) -> None:
    """选择 LeagueClient 目录时应回推到客户端根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "LeagueClient")

    assert result.resolved is True
    assert result.root == root


def test_resolves_lcu_plugin_directory(tmp_path: Path) -> None:
    """选择 LCU 插件目录时应回推到客户端根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data")

    assert result.resolved is True
    assert result.root == root


def test_resolves_champions_resource_directory(tmp_path: Path) -> None:
    """选择英雄资源目录时应回推到客户端根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "Game" / "DATA" / "FINAL" / "Champions")

    assert result.resolved is True
    assert result.root == root


def test_resolves_maps_shipping_directory(tmp_path: Path) -> None:
    """选择地图资源目录时应回推到客户端根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping")

    assert result.resolved is True
    assert result.root == root


def test_resolves_game_binary_file_path(tmp_path: Path) -> None:
    """直接传入游戏二进制文件路径时应支持后续入口复用。"""

    root = _write_game_root(tmp_path / "英雄联盟")

    result = resolve_game_path(root / "Game" / "League of Legends.exe")

    assert result.resolved is True
    assert result.root == root


def test_rejects_loose_binary_marker_without_metadata(tmp_path: Path) -> None:
    """不能只凭二进制文件名判定游戏目录。"""

    root = tmp_path / "英雄联盟"
    game_dir = root / "Game"
    game_dir.mkdir(parents=True)
    (game_dir / "League of Legends.exe").write_bytes(b"")

    result = resolve_game_path(root)

    assert result.resolved is False
    assert result.root is None
    assert result.reason == "not_found"


def test_reports_ambiguous_parent_with_multiple_game_roots(tmp_path: Path) -> None:
    """上级目录存在多个强匹配时不应静默猜测。"""

    parent = tmp_path / "WeGameApps"
    _write_game_root(parent / "英雄联盟")
    _write_game_root(parent / "英雄联盟-PBE", version="16.12.1")

    result = resolve_game_path(parent)

    assert result.resolved is False
    assert result.root is None
    assert result.reason == "ambiguous"
    assert {probe.root.name for probe in result.candidates} == {"英雄联盟", "英雄联盟-PBE"}


def test_invalid_path_returns_not_found(tmp_path: Path) -> None:
    """不存在的路径应返回未识别而不是抛出异常。"""

    result = resolve_game_path(tmp_path / "missing")

    assert result.resolved is False
    assert result.root is None
    assert result.reason == "not_found"
