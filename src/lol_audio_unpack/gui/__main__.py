from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QApplication

from lol_audio_unpack.gui.window import MainWindow
from lol_audio_unpack.gui.common import GuiConfig
from qfluentwidgets import setTheme, Theme, qconfig, setThemeColor


def main() -> None:
    # 启用高 DPI 缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)

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
