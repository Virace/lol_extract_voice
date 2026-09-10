"""提前准备数据开关的持久化与运行期锁定测试。"""

from lol_audio_unpack.gui.common.gui_config import GuiConfig
from lol_audio_unpack.gui.view.setting_page import SettingPage


def test_preparation_switch_persists_and_notifies_context(qtbot) -> None:
    """用户切换开关后保存偏好并通知共享状态；忙碌时遵守设置锁。"""
    page = SettingPage()
    qtbot.addWidget(page)
    assert not page.prepareDataCard.isChecked()

    for enabled in (True, False):
        with qtbot.waitSignal(page.shared_context_input_changed):
            page.prepareDataCard.setChecked(enabled)
        reloaded = GuiConfig()
        reloaded.load()
        assert reloaded.prepare_data_on_startup is enabled

    page.set_runtime_config_locked(True)
    assert not page.prepareDataCard.isEnabled()
    page.set_runtime_config_locked(False)
    assert page.prepareDataCard.isEnabled()
