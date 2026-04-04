"""`unpack.stats` 公开类型锚点测试。"""

from __future__ import annotations

from lol_audio_unpack.unpack.stats import FileProcessResult, ProcessingStatsContext


def test_unpack_stats_module_keeps_expected_public_types() -> None:
    """迁移前应继续暴露当前公开类型。"""

    assert FileProcessResult.SUCCESS.value == "success"
    assert ProcessingStatsContext is not None
