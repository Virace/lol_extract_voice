from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme, setThemeColor

from lol_audio_unpack.gui.common import GuiConfig
from lol_audio_unpack.gui.window import MainWindow
from lol_audio_unpack.utils.logging import setup_logging


def main() -> None:
    logger.enable("lol_audio_unpack")
    # 显式启用项目命名空间日志，并初始化基础日志系统到当前目录下的 .logs 文件夹
    setup_logging(
        dev_mode=True,
        log_level="INFO",
        log_file_path=Path.cwd() / ".logs",
        show_function_info=True,
    )
    logger.info("GUI 启动")

    # 启用高 DPI 缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    logger.debug("QApplication 创建完成")

    # 彻底解决 Windows 下中文 HighDPI 渲染 "横线发虚/掉底" 问题
    font = QFont("Microsoft YaHei")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Normal)
    # 关闭字体微调 (Hinting) 强制使用纯抗锯齿渲染，以避免小数缩放时笔画对齐引起的横线丢失
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    # 从 GuiConfig 加载并应用主题配置
    cfg = GuiConfig()
    cfg.load()

    theme_map = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
    theme = theme_map.get(cfg.theme_mode, Theme.LIGHT)
    qconfig.set(qconfig.themeMode, theme)
    setTheme(theme)

    color = QColor(cfg.theme_color)
    qconfig.set(qconfig.themeColor, color)
    setThemeColor(color)

    # 获取桌面并应用大小
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
