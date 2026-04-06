"""设置页路径选择 helper 测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.common import format_default_relative_path
from lol_audio_unpack.gui.controllers.path_picker import apply_path_card_label


def test_apply_path_card_label_uses_current_prefix_for_explicit_path() -> None:
    events: list[str] = []

    class _FakeCard:
        def setContent(self, text: str) -> None:
            events.append(text)

    apply_path_card_label(_FakeCard(), "foo/bar", default="")

    assert events == [f"当前: {format_default_relative_path('foo/bar')}"]


def test_apply_path_card_label_uses_default_prefix_when_path_missing() -> None:
    events: list[str] = []

    class _FakeCard:
        def setContent(self, text: str) -> None:
            events.append(text)

    apply_path_card_label(_FakeCard(), "", default="./output")

    assert events == [f"默认: {format_default_relative_path('./output')}"]
