"""测试设置页中的日志等级配置。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QLabel

import lol_audio_unpack.gui.view.setting_page as setting_page_module
from lol_audio_unpack.gui.common import gui_config as gui_config_module
from lol_audio_unpack.gui.view.setting_page import LogLevelSettingCard, SettingPage
from lol_audio_unpack.utils.runtime_paths import (
    detect_runtime_paths,
    get_default_vgmstream_relative_path,
)

DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT = 10
UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT = 35
DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY = "default"
UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY = "device:realtek"


class FakeQSettings:
    class Format:
        IniFormat = object()

    class Scope:
        UserScope = object()

    _store: dict[str, str] = {}

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def value(self, key: str, default=None):
        return self._store.get(key, default)

    def setValue(self, key: str, value) -> None:
        self._store[key] = value


def _use_fake_qsettings(monkeypatch) -> None:
    FakeQSettings._store = {}
    monkeypatch.setattr(gui_config_module, "QSettings", FakeQSettings)


def test_setting_page_warns_when_console_log_level_set_to_debug(monkeypatch, tmp_path: Path) -> None:
    """控制台日志切到 DEBUG 时应弹出性能提示。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    warning_calls: list[tuple[str, str]] = []

    class FakeMessageBox:
        def __init__(self, title: str, content: str, parent=None):
            _ = parent
            warning_calls.append((title, content))
            self.yesButton = type("YesButton", (), {"setText": staticmethod(lambda _text: None)})()

        def hideCancelButton(self) -> None:
            return None

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(setting_page_module, "MessageBox", FakeMessageBox)

    page = SettingPage()
    try:
        page.consoleLogLevelCard.comboBox.setCurrentText("DEBUG")
        app.processEvents()

        assert warning_calls
        assert page.config.console_log_level == "DEBUG"
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_file_log_level_does_not_show_warning(monkeypatch, tmp_path: Path) -> None:
    """仅修改文件日志等级时不应弹出性能提示。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    warning_calls: list[tuple[str, str]] = []

    class FakeMessageBox:
        def __init__(self, title: str, content: str, parent=None):
            _ = parent
            warning_calls.append((title, content))
            self.yesButton = type("YesButton", (), {"setText": staticmethod(lambda _text: None)})()

        def hideCancelButton(self) -> None:
            return None

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(setting_page_module, "MessageBox", FakeMessageBox)

    page = SettingPage()
    try:
        page.fileLogLevelCard.comboBox.setCurrentText("TRACE")
        app.processEvents()

        assert warning_calls == []
        assert page.config.file_log_level == "TRACE"
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_emits_shared_context_input_changed_after_runtime_save(monkeypatch, tmp_path: Path) -> None:
    """保存共享运行配置后应发出更明确的共享上下文变更信号。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    page = SettingPage()
    changed_events: list[bool] = []

    try:
        page.shared_context_input_changed.connect(lambda: changed_events.append(True))
        page._save_config()
        app.processEvents()

        assert changed_events == [True]
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_dialogs_use_runtime_resolved_initial_paths(monkeypatch, tmp_path: Path) -> None:
    """设置页文件选择器应以 runtime 解析后的绝对路径作为初始位置。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    runtime_root = tmp_path / "runtime-root"
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        gui_config_module,
        "detect_runtime_paths",
        lambda: detect_runtime_paths(
            is_frozen=True,
            cwd=tmp_path / "shortcut-workdir",
            executable=runtime_root / "LolAudioUnpack.exe",
        ),
    )

    directory_currents: list[str] = []
    file_currents: list[str] = []
    monkeypatch.setattr(
        setting_page_module.QFileDialog,
        "getExistingDirectory",
        lambda *_args, **_kwargs: directory_currents.append(_args[2]) or "",
    )
    monkeypatch.setattr(
        setting_page_module.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (file_currents.append(_args[2]) or "", ""),
    )

    app = QApplication.instance() or QApplication([])
    page = SettingPage()

    try:
        page.config.game_path = r".\game-client"
        page.config.output_path = r".\custom-output"
        page.config.wwiser_path = r".\tools\wwiser\wwiser.pyz"
        page.config.vgmstream_path = r".\tools\vgmstream\vgmstream-cli.exe"

        page._pick_game_path()
        page._pick_output_path()
        page._pick_wwiser()
        page._pick_vgmstream()
        app.processEvents()

        assert directory_currents == [
            str(runtime_root / "game-client"),
            str(runtime_root / "custom-output"),
        ]
        assert file_currents == [
            str(runtime_root / "tools" / "wwiser" / "wwiser.pyz"),
            str(runtime_root / "tools" / "vgmstream" / "vgmstream-cli.exe"),
        ]
    finally:
        page.deleteLater()
        app.processEvents()


def test_log_level_setting_card_captions_reuse_non_wrapping_subtitle_style() -> None:
    """日志等级手风琴内的说明文字应复用不自动换行的副标题样式。"""
    card = LogLevelSettingCard()

    target_labels = [
        label
        for label in card.findChildren(QLabel)
        if "全局日志面板" in label.text() or "输出目录 logs" in label.text()
    ]

    assert target_labels
    assert all(label.wordWrap() is False for label in target_labels)
    assert all(label.objectName() == "contentLabel" for label in target_labels)


def test_setting_page_renders_page_header(monkeypatch, tmp_path: Path) -> None:
    """设置页应展示主标题与简短说明。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    page = SettingPage()

    try:
        labels = [label.text() for label in page.findChildren(QLabel)]
        assert "全局设置" in labels
        assert "统一管理运行环境、工具路径与界面偏好。" in labels
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_apply_path_label_formats_default_root_relative_path() -> None:
    """设置页默认路径文案应显示为平台风格的根目录提示。"""
    card = Mock()
    default_relative_path = f"./{get_default_vgmstream_relative_path()}"

    SettingPage._apply_path_label(card, "", default_relative_path)

    expected = f"默认: {setting_page_module.format_default_relative_path(default_relative_path)}"
    card.setContent.assert_called_once_with(expected)


def test_setting_page_apply_path_label_formats_actual_path_for_display() -> None:
    """设置页当前路径文案应按显示层格式规范化分隔符。"""
    card = Mock()

    SettingPage._apply_path_label(card, "tools/wwiser/wwiser.pyz")

    card.setContent.assert_called_once_with(r"当前: tools\wwiser\wwiser.pyz")


def test_setting_page_apply_path_label_formats_relative_runtime_path() -> None:
    """设置页当前相对路径文案也应显示为基于根目录的提示。"""
    card = Mock()

    SettingPage._apply_path_label(card, r".\reconfigured-output")

    card.setContent.assert_called_once_with(r"当前: 根目录\reconfigured-output")


def test_setting_page_preview_audio_volume_slider_defaults_to_ten_percent(monkeypatch, tmp_path: Path) -> None:
    """试听音量滑块应默认加载为 10%。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    page = SettingPage()

    try:
        assert page.previewAudioVolumeCard.slider.value() == DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT
        assert page.previewAudioVolumeCard.valueLabel.text() == f"{DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT}%"
        assert page.config.preview_audio_volume_percent == DEFAULT_PREVIEW_AUDIO_VOLUME_PERCENT
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_preview_audio_volume_slider_updates_config_and_signal(monkeypatch, tmp_path: Path) -> None:
    """试听音量滑块变化后应即时写回配置并发出通知。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    page = SettingPage()
    emitted_values: list[int] = []

    try:
        page.preview_audio_volume_changed.connect(emitted_values.append)
        page.previewAudioVolumeCard.slider.setValue(UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT)
        app.processEvents()

        assert page.previewAudioVolumeCard.valueLabel.text() == f"{UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT}%"
        assert page.config.preview_audio_volume_percent == UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT
        assert FakeQSettings._store["preview_audio_volume_percent"] == UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT
        assert emitted_values == [UPDATED_PREVIEW_AUDIO_VOLUME_PERCENT]
    finally:
        page.deleteLater()
        app.processEvents()


def test_setting_page_preview_audio_output_device_defaults_to_default(monkeypatch, tmp_path: Path) -> None:
    """播放设备下拉框应默认选中“默认设备”。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        setting_page_module,
        "get_preview_audio_output_device_options",
        lambda: [
            ("默认设备", DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY),
            ("扬声器 (Realtek)", UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY),
        ],
    )
    page = SettingPage()

    try:
        assert page.previewAudioOutputDeviceCard.displayValue() == "默认设备"
        assert page.config.preview_audio_output_device_key == DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
    finally:
        page._disconnect_theme_persistence_signals()
        page.deleteLater()
        app.processEvents()


def test_setting_page_preview_audio_output_device_updates_config_and_signal(monkeypatch, tmp_path: Path) -> None:
    """播放设备下拉变化后应即时写回配置并发出通知。"""
    monkeypatch.chdir(tmp_path)
    _use_fake_qsettings(monkeypatch)
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        setting_page_module,
        "get_preview_audio_output_device_options",
        lambda: [
            ("默认设备", DEFAULT_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY),
            ("扬声器 (Realtek)", UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY),
        ],
    )
    page = SettingPage()
    emitted_values: list[str] = []

    try:
        page.preview_audio_output_device_changed.connect(emitted_values.append)
        page.previewAudioOutputDeviceCard.comboBox.setCurrentText("扬声器 (Realtek)")
        app.processEvents()

        assert page.config.preview_audio_output_device_key == UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
        assert FakeQSettings._store["preview_audio_output_device_key"] == UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY
        assert emitted_values == [UPDATED_PREVIEW_AUDIO_OUTPUT_DEVICE_KEY]
    finally:
        page._disconnect_theme_persistence_signals()
        page.deleteLater()
        app.processEvents()
