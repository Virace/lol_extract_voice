from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFileDialog

from qfluentwidgets import (
    SmoothScrollArea,
    SettingCardGroup,
    SettingCard,
    ExpandGroupSettingCard,
    PushSettingCard,
    SwitchSettingCard,
    OptionsSettingCard,
    CustomColorSettingCard,
    FluentIcon as FIF,
    ExpandLayout,
    ComboBox,
    LineEdit,
    BodyLabel,
    CaptionLabel,
    qconfig,
)

from lol_audio_unpack.gui.common import GuiConfig


# ---------------------------------------------------------------------------
# 辅助：右侧嵌入 ComboBox 的 SettingCard
# ---------------------------------------------------------------------------

class ComboRowSettingCard(SettingCard):
    """SettingCard with a ComboBox on the right — no qconfig binding.

    Args:
        items:      显示用的字符串列表。
        label_map:  可选 {显示文字: 实际值} 映射；不传则显示文字即实际值。
    """

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        items: list[str],
        label_map: dict[str, str] | None = None,
        parent=None,
    ):
        super().__init__(icon, title, content, parent)
        self._label_map = label_map or {}
        self.comboBox = ComboBox(self)
        self.comboBox.addItems(items)
        self.comboBox.setFixedWidth(180)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        """返回当前选项（若有映射则返回实际值，否则返回显示文字）。"""
        label = self.comboBox.currentText()
        return self._label_map.get(label, label)

    def setValue(self, text: str):
        """按实际值或显示文字定位选项。"""
        # 先按实际值反查 label
        reverse = {v: k for k, v in self._label_map.items()}
        label = reverse.get(text, text)
        idx = self.comboBox.findText(label)
        if idx >= 0:
            self.comboBox.setCurrentIndex(idx)

    def displayValue(self) -> str:
        """返回 ComboBox 当前的显示文字。"""
        return self.comboBox.currentText()


# ---------------------------------------------------------------------------
# 辅助：右侧嵌入 LineEdit 的 SettingCard
# ---------------------------------------------------------------------------

class LineEditSettingCard(SettingCard):
    """SettingCard with a LineEdit on the right."""

    def __init__(self, icon, title: str, content: str, placeholder: str = "", parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setFixedWidth(320)
        self.lineEdit.setClearButtonEnabled(True)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def value(self) -> str:
        return self.lineEdit.text().strip()

    def setValue(self, text: str):
        self.lineEdit.setText(text)


# ---------------------------------------------------------------------------
# 固定快照可折叠卡（ExpandGroupSettingCard 子类）
# ---------------------------------------------------------------------------

class FixedSnapshotCard(ExpandGroupSettingCard):
    """
    可折叠的固定快照配置组。
    展开后显示版本号、LCU URL、Game URL 三个输入行。
    三项必须同时填写，否则忽略，程序将自动解析最新快照。
    """

    def __init__(self, parent=None):
        super().__init__(
            FIF.PIN,
            "固定快照（高阶）",
            "锁定指定版本的远端快照；三项必须同时填写，留空则自动获取最新",
            parent,
        )

        # 内部调整：去掉多余的内边距让行高一致
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)

        # 三个输入控件
        self.versionEdit = LineEdit()
        self.versionEdit.setPlaceholderText("例: 15.5.1")
        self.versionEdit.setFixedWidth(240)
        self.versionEdit.setClearButtonEnabled(True)

        self.lcuUrlEdit = LineEdit()
        self.lcuUrlEdit.setPlaceholderText("https://...")
        self.lcuUrlEdit.setFixedWidth(360)
        self.lcuUrlEdit.setClearButtonEnabled(True)

        self.gameUrlEdit = LineEdit()
        self.gameUrlEdit.setPlaceholderText("https://...")
        self.gameUrlEdit.setFixedWidth(360)
        self.gameUrlEdit.setClearButtonEnabled(True)

        self._add_row("版本号", "REMOTE_VERSION", self.versionEdit)
        self._add_row("LCU Manifest URL", "REMOTE_LCU_MANIFEST_URL", self.lcuUrlEdit)
        self._add_row("Game Manifest URL", "REMOTE_GAME_MANIFEST_URL", self.gameUrlEdit)

    def _add_row(self, label_text: str, key_text: str, widget: QWidget):
        """添加 label + 右侧输入控件的行。"""
        row = QWidget()
        row.setFixedHeight(68)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(48, 12, 48, 12)

        v = QVBoxLayout()
        v.setSpacing(2)
        v.addWidget(BodyLabel(label_text))
        key_label = CaptionLabel(key_text)
        key_label.setObjectName("keyLabel")
        v.addWidget(key_label)

        layout.addLayout(v)
        layout.addStretch(1)
        layout.addWidget(widget)

        self.addGroupWidget(row)

    # 值读写

    def versionValue(self) -> str:
        return self.versionEdit.text().strip()

    def lcuUrlValue(self) -> str:
        return self.lcuUrlEdit.text().strip()

    def gameUrlValue(self) -> str:
        return self.gameUrlEdit.text().strip()

    def isComplete(self) -> bool:
        """三项都填写才算有效的固定快照设置。"""
        return bool(self.versionValue() and self.lcuUrlValue() and self.gameUrlValue())

    def setValues(self, version: str, lcu_url: str, game_url: str) -> None:
        self.versionEdit.setText(version)
        self.lcuUrlEdit.setText(lcu_url)
        self.gameUrlEdit.setText(game_url)


# ---------------------------------------------------------------------------
# SettingPage
# ---------------------------------------------------------------------------

class SettingPage(SmoothScrollArea):
    """Settings Page — all persistent config in one scrollable view."""

    # 路径变更信号
    game_path_changed = Signal(str)
    output_path_changed = Signal(str)
    wwiser_path_changed = Signal(str)
    vgmstream_path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SettingPage")
        self.view = QWidget(self)
        self.view.setObjectName("SettingPageView")
        self.view.setStyleSheet("QWidget#SettingPageView{background: transparent}")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        # 配置对象：先建好再构建 UI，确保 load() 后可立即应用
        self._cfg = GuiConfig()

        self._build_ui()
        self._load_config()
        self._connect_signals()

        # 初始化时根据当前模式刷新动态显隐
        self._on_source_mode_changed(self.sourceModeCard.displayValue())

    # ------------------------------------------------------------------
    # UI 建造
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.expandLayout = ExpandLayout(self.view)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.setSpacing(28)

        self._build_source_group()   # 1. 数据来源（动态显隐子组）
        self._build_base_group()     # 2. 基础设置
        self._build_tools_group()    # 3. 工具配置
        self._build_personal_group() # 4. 个性化

    # 1. 数据来源 -------------------------------------------------------

    # 来源模式：显示文字 → 实际 env 值的映射
    _SOURCE_MODE_MAP = {
        "本地模式": "local_path",
        "远程模式": "remote_snapshot",
    }

    def _build_source_group(self):
        # 1-A 模式选择（始终可见）
        self.sourceModeGroup = SettingCardGroup("数据来源", self.view)
        self.sourceModeCard = ComboRowSettingCard(
            FIF.CLOUD,
            "来源模式",
            "本地模式使用已安装的游戏目录；远程模式根据所提供的信息自动下载所需文件",
            list(self._SOURCE_MODE_MAP.keys()),
            label_map=self._SOURCE_MODE_MAP,
        )
        self.sourceModeGroup.addSettingCard(self.sourceModeCard)
        self.expandLayout.addWidget(self.sourceModeGroup)

        # 1-B Local 子组（本地模式时显示）
        self.localGroup = SettingCardGroup("本地目录", self.view)
        self.gamePathCard = PushSettingCard(
            "选择文件夹",
            FIF.FOLDER,
            "游戏根目录",
            "当前: 未设置",
        )
        self.localGroup.addSettingCard(self.gamePathCard)
        self.expandLayout.addWidget(self.localGroup)

        # 1-C Remote 子组（远程模式时显示）
        self.remoteGroup = SettingCardGroup("远程配置", self.view)

        self.remoteLiveRegionCard = ComboRowSettingCard(
            FIF.GLOBE,
            "Live 区服",
            "自动解析最新快照使用的 Riot 区服（默认 EUW，速度最稳定）",
            ["EUW", "NA", "KR", "JP", "BR", "TR", "RU", "OCE", "EUNE", "LAN", "LAS", "ME"],
        )
        self.cleanupRemoteCard = SwitchSettingCard(
            FIF.DELETE,
            "完成后自动清理",
            "删除远程下载的阶段性冗余文件，保持输出目录整洁",
        )
        # 固定快照三元组 — 折叠在 ExpandGroupSettingCard 中
        self.fixedSnapshotCard = FixedSnapshotCard()

        self.remoteGroup.addSettingCard(self.remoteLiveRegionCard)
        self.remoteGroup.addSettingCard(self.cleanupRemoteCard)
        self.remoteGroup.addSettingCard(self.fixedSnapshotCard)
        self.expandLayout.addWidget(self.remoteGroup)

    # 2. 基础设置 -------------------------------------------------------

    def _build_base_group(self):
        self.baseGroup = SettingCardGroup("基础设置", self.view)

        self.outputPathCard = PushSettingCard(
            "选择文件夹",
            FIF.FOLDER,
            "解包输出目录",
            "当前: 未设置",
        )
        self.gameRegionCard = ComboRowSettingCard(
            FIF.LANGUAGE,
            "游戏区域",
            "语音文件的区域标识，影响实际加载的语音资源",
            ["zh_CN", "en_US", "ja_JP", "ko_KR", "fr_FR", "de_DE", "es_ES", "pt_BR", "ru_RU"],
        )
        self.groupByTypeCard = SwitchSettingCard(
            FIF.FOLDER,
            "按类型分组输出",
            "开: audios/类型/英雄/…   关(默认): audios/英雄/类型/…",
        )

        self.baseGroup.addSettingCard(self.outputPathCard)
        self.baseGroup.addSettingCard(self.gameRegionCard)
        self.baseGroup.addSettingCard(self.groupByTypeCard)
        self.expandLayout.addWidget(self.baseGroup)

    # 3. 工具配置 -------------------------------------------------------

    def _build_tools_group(self):
        self.toolsGroup = SettingCardGroup("工具配置", self.view)

        self.wwiserCard = PushSettingCard(
            "选择文件",
            FIF.DEVELOPER_TOOLS,
            "wwiser 路径",
            "Mapping 功能依赖此工具 (wwiser.py)  —  https://github.com/bnnm/wwiser",
        )
        self.vgmstreamCard = PushSettingCard(
            "选择文件",
            FIF.COMMAND_PROMPT,
            "vgmstream-cli 路径",
            "音频转码依赖此工具 (vgmstream-cli.exe)  —  解包 .wem → .wav 格式",
        )

        self.toolsGroup.addSettingCard(self.wwiserCard)
        self.toolsGroup.addSettingCard(self.vgmstreamCard)
        self.expandLayout.addWidget(self.toolsGroup)

    # 4. 个性化 ---------------------------------------------------------

    def _build_personal_group(self):
        self.personalGroup = SettingCardGroup("个性化", self.view)

        self.themeCard = OptionsSettingCard(
            qconfig.themeMode,
            FIF.BRUSH,
            "应用主题",
            "设置界面的明暗模式",
            texts=["浅色", "深色", "跟随系统"],
            parent=self.personalGroup,
        )
        self.colorCard = CustomColorSettingCard(
            qconfig.themeColor,
            FIF.PALETTE,
            "主题颜色",
            "自定义应用的强调色",
            self.personalGroup,
        )
        # CustomColorSettingCard 内部文字通过 Qt 翻译机制生成，无中文翻译包；
        # 直接覆盖控件文字实现本地化。
        self.colorCard.defaultRadioButton.setText("默认颜色")
        self.colorCard.customRadioButton.setText("自定义颜色")
        self.colorCard.customLabel.setText("自定义颜色")
        self.colorCard.chooseColorButton.setText("选择颜色")
        # 同步右侧提示标签
        self.colorCard.choiceLabel.setText(self.colorCard.buttonGroup.checkedButton().text())
        self.colorCard.choiceLabel.adjustSize()

        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.colorCard)
        self.expandLayout.addWidget(self.personalGroup)

    # ------------------------------------------------------------------
    # 配置加载 / 保存
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """从 GuiConfig 读取保存的配置并应用到各控件。"""
        cfg = self._cfg
        cfg.load()

        # 来源模式
        self.sourceModeCard.setValue(cfg.source_mode)

        # 游戏路径
        self._apply_path_label(self.gamePathCard, cfg.game_path)

        # 远程配置
        self.remoteLiveRegionCard.setValue(cfg.remote_live_region)
        self.cleanupRemoteCard.setChecked(cfg.cleanup_remote)
        self.fixedSnapshotCard.setValues(
            cfg.snapshot_version, cfg.snapshot_lcu_url, cfg.snapshot_game_url
        )

        # 基础设置
        self._apply_path_label(self.outputPathCard, cfg.output_path, r".\output")
        self.gameRegionCard.setValue(cfg.game_region)
        self.groupByTypeCard.setChecked(cfg.group_by_type)

        # 工具配置
        self._apply_path_label(self.wwiserCard, cfg.wwiser_path, r".\tools\wwiser\wwiser.pyz")
        self._apply_path_label(self.vgmstreamCard, cfg.vgmstream_path, r".\tools\vgmstream\vgmstream-cli.exe")

        # 个性化 — 应用已保存的主题
        self._apply_theme_from_config()

    def _save_config(self) -> None:
        """将各控件当前值写入 GuiConfig 并持久化。"""
        cfg = self._cfg

        cfg.source_mode = self.sourceModeCard.value()
        cfg.remote_live_region = self.remoteLiveRegionCard.value()
        cfg.cleanup_remote = self.cleanupRemoteCard.isChecked()
        cfg.snapshot_version = self.fixedSnapshotCard.versionValue()
        cfg.snapshot_lcu_url = self.fixedSnapshotCard.lcuUrlValue()
        cfg.snapshot_game_url = self.fixedSnapshotCard.gameUrlValue()
        cfg.game_region = self.gameRegionCard.value()
        cfg.group_by_type = self.groupByTypeCard.isChecked()

        cfg.save()

    def _save_theme_config(self) -> None:
        """保存主题配置到 GuiConfig。"""
        from qfluentwidgets import Theme
        cfg = self._cfg
        # 从 qconfig 读取当前主题设置
        theme_map = {Theme.LIGHT: "Light", Theme.DARK: "Dark", Theme.AUTO: "Auto"}
        cfg.theme_mode = theme_map.get(qconfig.themeMode.value, "Light")
        cfg.theme_color = qconfig.themeColor.value.name()
        cfg.save()

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """连接所有控件的变更信号，实现即时持久化。"""
        # 来源模式 — 同时控制显隐
        self.sourceModeCard.comboBox.currentTextChanged.connect(self._on_source_mode_changed)
        self.sourceModeCard.comboBox.currentTextChanged.connect(self._save_config)

        # 目录 / 文件选择按钮
        self.gamePathCard.clicked.connect(self._pick_game_path)
        self.outputPathCard.clicked.connect(self._pick_output_path)
        self.wwiserCard.clicked.connect(self._pick_wwiser)
        self.vgmstreamCard.clicked.connect(self._pick_vgmstream)

        # 远程配置
        self.remoteLiveRegionCard.comboBox.currentTextChanged.connect(self._save_config)
        self.cleanupRemoteCard.checkedChanged.connect(self._save_config)
        self.fixedSnapshotCard.versionEdit.editingFinished.connect(self._save_config)
        self.fixedSnapshotCard.lcuUrlEdit.editingFinished.connect(self._save_config)
        self.fixedSnapshotCard.gameUrlEdit.editingFinished.connect(self._save_config)

        # 基础设置
        self.gameRegionCard.comboBox.currentTextChanged.connect(self._save_config)
        self.groupByTypeCard.checkedChanged.connect(self._save_config)

        # 个性化 — 主题变更时保存
        qconfig.themeChanged.connect(self._save_theme_config)
        qconfig.themeColorChanged.connect(self._save_theme_config)

    # ------------------------------------------------------------------
    # 目录 / 文件选择槽
    # ------------------------------------------------------------------

    def _pick_game_path(self) -> None:
        """弹出文件夹选择对话框，更新游戏根目录。"""
        current = self._cfg.game_path or ""
        path = QFileDialog.getExistingDirectory(
            self, "选择游戏根目录", current,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if path:
            self._cfg.game_path = path
            self._cfg.save()
            self._apply_path_label(self.gamePathCard, path)
            self.game_path_changed.emit(path)

    def _pick_output_path(self) -> None:
        """弹出文件夹选择对话框，更新解包输出目录。"""
        current = self._cfg.output_path or ""
        path = QFileDialog.getExistingDirectory(
            self, "选择解包输出目录", current,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if path:
            self._cfg.output_path = path
            self._cfg.save()
            self._apply_path_label(self.outputPathCard, path, r".\output")
            self.output_path_changed.emit(path)

    def _pick_wwiser(self) -> None:
        """弹出文件选择对话框，更新 wwiser.py 路径。"""
        current = self._cfg.wwiser_path or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 wwiser.py", current, "Python 脚本 (wwiser.py wwiser.pyz);;所有文件 (*)"
        )
        if path:
            self._cfg.wwiser_path = path
            self._cfg.save()
            self._apply_path_label(self.wwiserCard, path, r".\tools\wwiser\wwiser.pyz")
            self.wwiser_path_changed.emit(path)

    def _pick_vgmstream(self) -> None:
        """弹出文件选择对话框，更新 vgmstream-cli 路径。"""
        current = self._cfg.vgmstream_path or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 vgmstream-cli", current,
            "可执行文件 (vgmstream-cli.exe vgmstream-cli);;所有文件 (*)"
        )
        if path:
            self._cfg.vgmstream_path = path
            self._cfg.save()
            self._apply_path_label(self.vgmstreamCard, path, r".\tools\vgmstream\vgmstream-cli.exe")
            self.vgmstream_path_changed.emit(path)

    # ------------------------------------------------------------------
    # 动态显隐
    # ------------------------------------------------------------------

    def _on_source_mode_changed(self, label: str) -> None:
        """根据来源模式（显示文字）切换 local / remote 子组的可见性。"""
        is_local = (label == "本地模式")
        self.localGroup.setVisible(is_local)
        self.remoteGroup.setVisible(not is_local)

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _apply_theme_from_config(self) -> None:
        """从 GuiConfig 应用主题设置到 qconfig。"""
        from qfluentwidgets import Theme, setTheme, setThemeColor
        from PySide6.QtGui import QColor

        cfg = self._cfg
        # 应用主题模式
        theme_map = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
        theme = theme_map.get(cfg.theme_mode, Theme.LIGHT)
        qconfig.set(qconfig.themeMode, theme)
        setTheme(theme)

        # 应用主题颜色
        color = QColor(cfg.theme_color)
        qconfig.set(qconfig.themeColor, color)
        setThemeColor(color)

    @staticmethod
    def _apply_path_label(card: PushSettingCard, path: str, default: str = "") -> None:
        """将路径显示在卡片的 contentLabel 上；路径为空时显示默认值或"未设置"。"""
        if path:
            card.setContent(f"当前: {path}")
        elif default:
            card.setContent(f"默认: {default}")
        else:
            card.setContent("当前: 未设置")

    # ------------------------------------------------------------------
    # 公共值读取（供其他页面或 Worker 调用）
    # ------------------------------------------------------------------

    @property
    def config(self) -> GuiConfig:
        """返回当前已加载的 GuiConfig 对象（调用前请确保已 load()）。"""
        return self._cfg

    def source_mode_value(self) -> str:
        """返回来源模式的实际 env 值（local_path / remote_snapshot）。"""
        return self.sourceModeCard.value()
