"""验证 GUI 测试目录的自动分层标记。"""

import pytest


def test_gui_tests_get_gui_layer_marker(request: pytest.FixtureRequest) -> None:
    """GUI 目录测试应自动归入 gui 分层。"""
    marker_names = {marker.name for marker in request.node.iter_markers()}

    assert "gui" in marker_names
    assert "functional" not in marker_names
