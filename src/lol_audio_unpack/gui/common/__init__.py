"""GUI 公共能力导出。"""

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.common.log_bridge import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    clear_buffered_log_lines,
    get_buffered_log_lines,
    install_startup_log_buffer,
    remove_startup_log_buffer,
)
from lol_audio_unpack.gui.common.scrolling import apply_smooth_scroll_enabled

__all__ = [
    "GUI_LOG_FORMAT",
    "GUI_LOG_MAX_LINES",
    "GuiConfig",
    "apply_smooth_scroll_enabled",
    "clear_buffered_log_lines",
    "get_buffered_log_lines",
    "install_startup_log_buffer",
    "remove_startup_log_buffer",
]
