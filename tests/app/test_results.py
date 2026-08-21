"""应用工作流 typed result 的聚合合同测试。"""

from __future__ import annotations

import pytest

from lol_audio_unpack.app.results import EntityResult, ResultStatus, RunResult, StageResult

pytestmark = pytest.mark.unit


def _entity(status: ResultStatus, entity_id: str = "1") -> EntityResult:
    return EntityResult("champion", entity_id, status, entity_name=f"Champion {entity_id}")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), ResultStatus.SUCCESS),
        ((ResultStatus.SUCCESS,), ResultStatus.SUCCESS),
        ((ResultStatus.FAILED,), ResultStatus.FAILED),
        ((ResultStatus.SUCCESS, ResultStatus.FAILED), ResultStatus.PARTIAL),
        ((ResultStatus.PARTIAL, ResultStatus.FAILED), ResultStatus.PARTIAL),
        ((ResultStatus.SUCCESS, ResultStatus.CANCELLED), ResultStatus.CANCELLED),
    ],
)
def test_stage_status_is_derived_from_entities(statuses, expected):
    entities = tuple(_entity(status, str(index)) for index, status in enumerate(statuses))

    result = StageResult.from_entities("extract", entities)

    assert result.status is expected


def test_stage_error_is_failed_without_entities_and_partial_after_success():
    failed = StageResult.from_error("update", RuntimeError("disk full"))
    partial = StageResult.from_error(
        "extract", RuntimeError("worker stopped"), entities=(_entity(ResultStatus.SUCCESS),)
    )

    assert failed.status is ResultStatus.FAILED
    assert failed.error_type == "RuntimeError"
    assert failed.error_message == "disk full"
    assert partial.status is ResultStatus.PARTIAL


def test_stage_can_represent_external_partial_summary_without_item_details():
    result = StageResult("wav", status=ResultStatus.PARTIAL, note="1 个文件转换失败")

    assert result.status is ResultStatus.PARTIAL
    assert result.total_count == 0


def test_stage_counts_are_derived_from_entities():
    entities = (
        _entity(ResultStatus.SUCCESS, "1"),
        _entity(ResultStatus.PARTIAL, "2"),
        _entity(ResultStatus.FAILED, "3"),
        _entity(ResultStatus.CANCELLED, "4"),
    )
    result = StageResult.from_entities("mapping", entities)

    assert result.total_count == len(entities)
    assert result.success_count == 1
    assert result.partial_count == 1
    assert result.failed_count == 1
    assert result.cancelled_count == 1


def test_stage_combine_preserves_child_order_and_stage_status():
    first = StageResult.from_entities("extract", (_entity(ResultStatus.SUCCESS, "1"),))
    second = StageResult.from_error(
        "extract",
        RuntimeError("worker stopped"),
        entities=(_entity(ResultStatus.FAILED, "2"),),
        note="地图批次中断",
    )

    result = StageResult.combine("extract", (first, second))

    assert result.status is ResultStatus.PARTIAL
    assert tuple(entity.entity_id for entity in result.entities) == ("1", "2")
    assert result.error_type == "RuntimeError"
    assert result.error_message == "worker stopped"
    assert result.note == "地图批次中断"


def test_stage_combine_empty_children_is_success_no_op():
    result = StageResult.combine("mapping", (), note="没有待处理实体")

    assert result.status is ResultStatus.SUCCESS
    assert result.entities == ()
    assert result.note == "没有待处理实体"


def test_entity_error_keeps_stable_text_without_exception_object():
    error = ValueError("未知英雄")

    result = EntityResult.from_error("champion", "999", error, entity_name="Unknown")

    assert result.status is ResultStatus.FAILED
    assert result.error_type == "ValueError"
    assert result.error_message == "未知英雄"
    assert not hasattr(result, "__dict__")


@pytest.mark.parametrize(
    ("stages", "expected"),
    [
        ((), ResultStatus.SUCCESS),
        ((StageResult("update"),), ResultStatus.SUCCESS),
        ((StageResult.from_error("update", RuntimeError("boom")),), ResultStatus.FAILED),
        (
            (StageResult("update"), StageResult.from_error("extract", RuntimeError("boom"))),
            ResultStatus.PARTIAL,
        ),
        (
            (StageResult("update"), StageResult.cancelled("extract")),
            ResultStatus.CANCELLED,
        ),
    ],
)
def test_run_status_is_derived_from_stages(stages, expected):
    result = RunResult(stages)

    assert result.status is expected


def test_run_counts_are_derived_across_stages():
    stages = (
        StageResult.from_entities("extract", (_entity(ResultStatus.SUCCESS, "1"),)),
        StageResult.from_entities("mapping", (_entity(ResultStatus.FAILED, "2"),)),
    )
    result = RunResult(stages)

    assert result.stage_count == len(stages)
    assert result.total_count == len(stages)
    assert result.success_count == 1
    assert result.failed_count == 1
