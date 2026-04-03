"""CLI 文本目录模块测试。"""

import pytest

from lol_audio_unpack.cli import main as cli_main
from lol_audio_unpack.cli.text import DEFAULT_LOCALE, text


def test_default_locale_is_zh_cn() -> None:
    assert DEFAULT_LOCALE == "zh_CN"
    assert text("action.update") == "更新数据"


def test_text_returns_value_with_explicit_zh_cn() -> None:
    assert text("parser.unpack.description", locale="zh_CN") == "一个极简、高效的英雄联盟音频提取工具 (v3)"


def test_text_raises_clear_keyerror_when_key_missing() -> None:
    with pytest.raises(KeyError, match="cli text key"):
        text("missing.key")


def test_cli_package_main_is_callable() -> None:
    assert callable(cli_main)


def test_text_raises_clear_keyerror_for_unsupported_locale() -> None:
    with pytest.raises(KeyError, match="cli text key"):
        text("action.update", locale="en_US")
