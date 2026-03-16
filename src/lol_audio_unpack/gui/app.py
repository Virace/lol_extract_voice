"""Application bootstrap for the Fluent-based GUI shell."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from .services import GuiPreviewService
from .window import MainWindow


def start_gui_app(argv: Sequence[str] | None = None) -> int:
    """Start the Fluent GUI preview application.

    Args:
        argv: Optional command-line arguments.

    Returns:
        The Qt application exit code.
    """
    args = list(argv) if argv is not None else sys.argv
    app = QApplication(args)
    app.setApplicationName("lol_audio_unpack GUI")
    app.setOrganizationName("Virace")
    setTheme(Theme.DARK)

    preview_state = GuiPreviewService().load_preview_state()
    window = MainWindow(preview_state=preview_state)
    window.show()
    return app.exec()
