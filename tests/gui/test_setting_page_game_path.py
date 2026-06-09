"""设置页游戏目录选择测试。"""

from __future__ import annotations

import json
from pathlib import Path

from lol_audio_unpack.gui.view import setting_page as setting_page_module
from lol_audio_unpack.gui.view.setting_page import SettingPage


def _write_game_root(root: Path) -> Path:
    """写入最小可识别的游戏目录。"""

    game_dir = root / "Game"
    lcu_dir = root / "LeagueClient"
    (game_dir / "DATA" / "FINAL" / "Champions").mkdir(parents=True)
    (game_dir / "DATA" / "FINAL" / "Maps" / "Shipping").mkdir(parents=True)
    (lcu_dir / "Plugins" / "rcp-be-lol-game-data").mkdir(parents=True)
    (game_dir / "content-metadata.json").write_text(json.dumps({"version": "16.11.1"}), encoding="utf-8")
    (game_dir / "League of Legends.exe").write_bytes(b"")
    (lcu_dir / "LeagueClient.exe").write_bytes(b"")
    return root


def test_setting_page_game_picker_saves_normalized_root(qtbot, tmp_path: Path, monkeypatch) -> None:
    """用户选到 Game 目录时设置页应保存归一化后的根目录。"""

    root = _write_game_root(tmp_path / "英雄联盟")
    page = SettingPage()
    qtbot.addWidget(page)
    notices: list[dict[str, str]] = []
    changed: list[str] = []
    shared_changed: list[bool] = []
    page.game_path_changed.connect(changed.append)
    page.shared_context_input_changed.connect(lambda: shared_changed.append(True))
    monkeypatch.setattr(setting_page_module, "pick_directory", lambda **_kwargs: str(root / "Game"))
    monkeypatch.setattr(setting_page_module, "show_feedback_infobar", lambda **kwargs: notices.append(kwargs), raising=False)

    page._pick_game_path()

    assert Path(page.config.game_path) == root.resolve(strict=False)
    assert [Path(path) for path in changed] == [root.resolve(strict=False)]
    assert shared_changed == [True]
    assert notices[-1]["title"] == "已识别游戏目录"
    assert str(root.resolve(strict=False)) in notices[-1]["content"]


def test_setting_page_game_picker_keeps_previous_path_when_invalid(qtbot, tmp_path: Path, monkeypatch) -> None:
    """无法识别目录时不应覆盖已有游戏路径。"""

    previous = tmp_path / "previous"
    page = SettingPage()
    qtbot.addWidget(page)
    page.config.game_path = str(previous)
    changed: list[str] = []
    page.game_path_changed.connect(changed.append)
    monkeypatch.setattr(setting_page_module, "pick_directory", lambda **_kwargs: str(tmp_path / "invalid"))
    monkeypatch.setattr(setting_page_module, "show_feedback_infobar", lambda **_kwargs: None, raising=False)

    page._pick_game_path()

    assert page.config.game_path == str(previous)
    assert changed == []
