"""远端来源面板的载荷回归测试。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from lol_audio_unpack.gui.controllers.remote_source import RemoteSourceDraft
from lol_audio_unpack.gui.view.settings.remote_source_panel import RemoteSourcePanel


def test_remote_source_panel_draft_changed_emits_current_draft(qtbot) -> None:
    host = QWidget()
    panel = RemoteSourcePanel(host)
    qtbot.addWidget(host)
    panel.set_source_mode("remote_snapshot")

    received: list[RemoteSourceDraft] = []

    def _capture_draft(draft: RemoteSourceDraft) -> None:
        received.append(draft)

    panel.draft_changed.connect(_capture_draft)

    panel.liveRegionCard.setValue("KR")
    panel._emit_draft_changed()

    assert received
    assert received[-1] == RemoteSourceDraft(
        source_mode="remote_snapshot",
        strategy="latest",
        live_region="KR",
        cleanup_remote=False,
        snapshot_version="",
        snapshot_lcu_url="",
        snapshot_game_url="",
    )
