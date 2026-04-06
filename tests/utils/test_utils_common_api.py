"""`utils.common` 公开行为基线测试。"""

from __future__ import annotations

import lol_audio_unpack.utils.common as common_utils
from lol_audio_unpack.manager.data_reader import DataReader
from lol_audio_unpack.utils.common import Singleton, format_duration, sanitize_filename


def test_sanitize_filename_replaces_windows_illegal_chars() -> None:
    """非法字符应被替换为下划线。"""

    assert sanitize_filename('a<b>:c?.wem') == "a_b__c_.wem"


def test_format_duration_keeps_human_readable_thresholds() -> None:
    """耗时格式化应保持当前阈值行为。"""

    assert format_duration(800) == "800ms"
    assert format_duration(1500) == "1.5s (1500ms)"


def test_singleton_registry_exposes_data_reader_cache_slot() -> None:
    """单例注册表应继续暴露给当前测试与调用方。"""

    assert isinstance(Singleton._instances, dict)
    Singleton._instances.pop(DataReader, None)


def test_common_module_exports_trimmed_public_surface() -> None:
    """`common` 应显式声明当前保留的公开 API。"""

    assert common_utils.__all__ == [
        "Singleton",
        "dump_json",
        "dump_msgpack",
        "dump_yaml",
        "format_duration",
        "format_region",
        "load_json",
        "load_msgpack",
        "load_yaml",
        "sanitize_filename",
    ]
