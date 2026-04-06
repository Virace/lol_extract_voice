"""GUI 公共能力导出。"""

from lol_audio_unpack.gui.common.app_context_guard import get_block_reason
from lol_audio_unpack.gui.common.feedback import (
    calculate_feedback_duration,
    show_feedback_infobar,
)
from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.common.log_bridge import (
    GUI_LOG_FORMAT,
    GUI_LOG_MAX_LINES,
    clear_buffered_log_lines,
    get_buffered_log_lines,
    install_pyvgmstream_log_bridge,
    install_qt_message_bridge,
    install_startup_log_buffer,
    remove_startup_log_buffer,
)
from lol_audio_unpack.gui.common.remote_mode_policy import (
    available_source_mode_labels,
    is_remote_panel_visible,
    needs_remote_mode_fallback,
)
from lol_audio_unpack.gui.common.path_display import (
    format_default_relative_path,
    format_path_for_display,
)
from lol_audio_unpack.gui.common.scrolling import apply_smooth_scroll_enabled

__all__ = [
    "GUI_LOG_FORMAT",
    "GUI_LOG_MAX_LINES",
    "GuiConfig",
    "available_source_mode_labels",
    "apply_smooth_scroll_enabled",
    "calculate_feedback_duration",
    "clear_buffered_log_lines",
    "format_default_relative_path",
    "format_path_for_display",
    "get_block_reason",
    "get_buffered_log_lines",
    "install_pyvgmstream_log_bridge",
    "install_qt_message_bridge",
    "install_startup_log_buffer",
    "needs_remote_mode_fallback",
    "remove_startup_log_buffer",
    "is_remote_panel_visible",
    "show_feedback_infobar",
]
