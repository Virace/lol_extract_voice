"""验证重试计划按失败阶段保留独立目标。"""

from lol_audio_unpack.app.failures import collect_failures
from lol_audio_unpack.app.results import EntityResult, ResultStatus, RunResult, StageResult
from lol_audio_unpack.gui.service.task_retry import build_retry_stages
from lol_audio_unpack.gui.task_models import ExecutionTaskParamsSnapshot


def test_retry_does_not_cross_product_entities_and_stages() -> None:
    """英雄一解包失败、英雄二映射失败时，不把两者组合成全阶段重跑。"""
    result = RunResult(
        tuple(
            StageResult.from_entities(stage, (EntityResult("champion", entity_id, ResultStatus.FAILED),))
            for stage, entity_id in (("extract", 1), ("mapping", 2))
        )
    )
    stages = build_retry_stages(
        ExecutionTaskParamsSnapshot(champion_ids=(1, 2), wav_enabled=True), collect_failures(result)
    )
    assert len(stages) == len(result.stages)
    assert stages[0].params.champion_ids == (1,)
    assert stages[0].params.selected_steps() == ("音频解包",)
    assert stages[1].params.champion_ids == (2,)
    assert stages[1].params.selected_steps() == ("事件映射",)
