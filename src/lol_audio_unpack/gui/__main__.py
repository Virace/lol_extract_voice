"""GUI 应用入口。"""

from __future__ import annotations

import sys
from time import perf_counter

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

from lol_audio_unpack.gui.common import (
    GuiConfig,
    install_startup_log_buffer,
    remove_startup_log_buffer,
)
from lol_audio_unpack.gui.controllers.contracts import RuntimeLoggingConfig
from lol_audio_unpack.gui.controllers.runtime_logging_session import (
    apply_runtime_logging_session,
)
from lol_audio_unpack.gui.window import MainWindow


def _log_startup_stage(stage: str, startup_begin: float, previous_mark: float) -> float:
    """记录 GUI 启动阶段耗时。

    Args:
        stage: 当前阶段名称。
        startup_begin: 启动开始时间戳。
        previous_mark: 上一阶段完成时间戳。

    Returns:
        当前阶段结束的时间戳。
    """
    current_mark = perf_counter()
    logger.trace(
        "GUI 启动阶段 | {} | 本段 {:.3f}s | 累计 {:.3f}s",
        stage,
        current_mark - previous_mark,
        current_mark - startup_begin,
    )
    return current_mark


def main() -> None:
    startup_begin = perf_counter()
    previous_mark = startup_begin
    cfg = GuiConfig()
    cfg.load()
    logger.enable("lol_audio_unpack")
    # GUI 启动期先建立一次会话级日志文件，后续同目录重配置沿用该文件。
    apply_runtime_logging_session(
        RuntimeLoggingConfig.from_gui_config(cfg),
        dev_mode=True,
        show_function_info=True,
    )
    install_startup_log_buffer()
    logger.info("GUI 启动")
    previous_mark = _log_startup_stage("setup_logging 完成", startup_begin, previous_mark)

    # 启用高 DPI 缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    previous_mark = _log_startup_stage("Qt HighDPI 属性配置完成", startup_begin, previous_mark)

    app = QApplication(sys.argv)
    previous_mark = _log_startup_stage("QApplication 创建完成", startup_begin, previous_mark)

    # 彻底解决 Windows 下中文 HighDPI 渲染 "横线发虚/掉底" 问题
    font = QFont("Microsoft YaHei")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    # 关闭字体微调 (Hinting) 强制使用纯抗锯齿渲染，以避免小数缩放时笔画对齐引起的横线丢失
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    previous_mark = _log_startup_stage("应用字体配置完成", startup_begin, previous_mark)

    # 从 GuiConfig 应用主题配置
    previous_mark = _log_startup_stage("GuiConfig 加载完成", startup_begin, previous_mark)

    theme_map = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
    theme = theme_map.get(cfg.theme_mode, Theme.LIGHT)
    qconfig.set(qconfig.themeMode, theme)
    setTheme(theme)

    color = QColor(cfg.theme_color)
    qconfig.set(qconfig.themeColor, color)
    setThemeColor(color)
    previous_mark = _log_startup_stage("主题与主题色应用完成", startup_begin, previous_mark)

    # 获取桌面并应用大小
    window = MainWindow()
    remove_startup_log_buffer()
    previous_mark = _log_startup_stage("MainWindow 构建完成", startup_begin, previous_mark)
    if not window.isVisible():
        window.show()
    previous_mark = _log_startup_stage("主窗口可见状态确认完成", startup_begin, previous_mark)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
