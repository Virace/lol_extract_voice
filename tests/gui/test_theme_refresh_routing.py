"""主题刷新路由回归测试。"""

from __future__ import annotations

import re
from pathlib import Path


def test_log_drawer_surface_refresh_only_tracks_theme_mode() -> None:
    """日志抽屉 surface 刷新不应继续绑定到 accent 变化。"""
    source = Path("src/lol_audio_unpack/gui/components/log_drawer.py").read_text(encoding="utf-8")
    init_match = re.search(
        r"def __init__\(self, parent: QWidget\) -> None:(?P<body>.*?)(?:\n    def |\Z)",
        source,
        re.DOTALL,
    )
    disconnect_match = re.search(
        r"def _disconnect_theme_surface_listeners\(self, \*_args: object\) -> None:(?P<body>.*?)(?:\n    def |\Z)",
        source,
        re.DOTALL,
    )

    assert init_match is not None
    assert disconnect_match is not None
    init_body = init_match.group("body")
    disconnect_body = disconnect_match.group("body")

    assert "qconfig.themeChanged.connect(self._theme_surface_listener)" in init_body
    assert "qconfig.themeColorChanged.connect" not in init_body
    assert "qconfig.themeChanged.disconnect(listener)" in disconnect_body
    assert "themeColorChanged" not in disconnect_body


def test_overview_page_splits_theme_and_accent_refresh_routes() -> None:
    """总览页应把壳层刷新与 accent 刷新拆开连接。"""
    source = Path("src/lol_audio_unpack/gui/view/overview_page.py").read_text(encoding="utf-8")
    setup_match = re.search(
        r"def _setup_connections\(self\) -> None:(?P<body>.*?)(?:\n    def |\Z)",
        source,
        re.DOTALL,
    )
    disconnect_match = re.search(
        r"def _disconnect_theme_refresh_listeners\(self, \*_args: object\) -> None:(?P<body>.*?)(?:\n    def |\Z)",
        source,
        re.DOTALL,
    )

    assert setup_match is not None
    assert disconnect_match is not None
    setup_body = setup_match.group("body")
    disconnect_body = disconnect_match.group("body")

    assert "qconfig.themeChanged.connect(self._refresh_theme_styles)" in setup_body
    assert "qconfig.themeColorChanged.connect(self._refresh_entity_list_theme)" in setup_body
    assert "(qconfig.themeChanged, self._refresh_theme_styles)" in disconnect_body
    assert "(qconfig.themeColorChanged, self._refresh_entity_list_theme)" in disconnect_body
