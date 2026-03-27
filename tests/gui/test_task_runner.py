"""测试执行中心后台任务运行器。"""

from __future__ import annotations

import lol_audio_unpack.gui.service.task_runner as task_runner_module
from lol_audio_unpack.gui.service.task_runner import run_execution_task
from lol_audio_unpack.gui.task_models import (
    AppContextInputSnapshot,
    ExecutionTaskDraft,
    ExecutionTaskParamsSnapshot,
    ExecutionTaskProgress,
    QueuedExecutionTask,
)


class _CapturedEmitter:
    """收集测试中的 signal emit 调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def emit(self, *args: object) -> None:
        """记录一次 emit。"""
        self.calls.append(args)


class _FakeSignals:
    """模拟 ``WorkerSignals`` 中当前测试关心的进度通道。"""

    def __init__(self) -> None:
        self.progress = _CapturedEmitter()


def test_run_execution_task_executes_backend_steps_in_order(monkeypatch, tmp_path) -> None:
    """运行器应按 update -> extract -> mapping 顺序调用后端门面。"""
    captured_overrides: dict[str, str | bool] = {}
    calls: list[tuple[object, ...]] = []
    sample_game_path = str(tmp_path / "game-root")
    sample_output_path = str(tmp_path / "output-root")

    class FakeApp:
        """记录后端门面调用顺序的替身。"""

        def __init__(self, ctx) -> None:
            calls.append(("init", ctx))

        def update(self, opts, *, target: str = "all") -> None:
            calls.append(("update", target, opts.max_workers, opts.force_update, opts.champion_ids, opts.map_ids))

        def extract(
            self,
            opts,
            *,
            include_champions: bool = True,
            include_maps: bool = True,
            progress_callback=None,
        ) -> None:
            calls.append(("extract", include_champions, include_maps, opts.integrate_data))
            if progress_callback is not None:
                progress_callback("champion", 1, 2, "Annie 解包完成")

        def mapping(
            self,
            opts,
            *,
            include_champions: bool = True,
            include_maps: bool = True,
            progress_callback=None,
        ) -> None:
            calls.append(("mapping", include_champions, include_maps, opts.integrate_data))
            if progress_callback is not None:
                progress_callback("map", 1, 1, "召唤师峡谷 映射完成")

    def fake_create_app_context(*, cli_overrides):
        captured_overrides.update(cli_overrides)
        return {"cli_overrides": dict(cli_overrides)}

    monkeypatch.setattr(task_runner_module, "create_app_context", fake_create_app_context)
    monkeypatch.setattr(task_runner_module, "LolAudioUnpackApp", FakeApp)

    task = QueuedExecutionTask(
        task_id=7,
        summary="音频解包 + 事件映射 · 目标：英雄 2 个，地图 1 个",
        draft=ExecutionTaskDraft(
            source="manual_input",
            source_summary="当前目标来自执行中心里的 ID 输入框。",
            context_input=AppContextInputSnapshot(
                overrides=(("GAME_PATH", sample_game_path), ("OUTPUT_PATH", sample_output_path)),
            ),
            task_params=ExecutionTaskParamsSnapshot(
                champion_ids=(1, 103),
                map_ids=(11,),
                run_update=True,
                run_extract=True,
                run_mapping=True,
                max_workers=8,
                with_bp_vo=False,
                exclude_types=("SFX", "MUSIC"),
                integrate_data=True,
            ),
        ),
    )
    signals = _FakeSignals()

    result = run_execution_task(task, signals)

    assert captured_overrides["GAME_PATH"] == sample_game_path
    assert captured_overrides["OUTPUT_PATH"] == sample_output_path
    assert captured_overrides["WITH_BP_VO"] is False
    assert captured_overrides["EXCLUDE_TYPE"] == "SFX,MUSIC"
    assert calls == [
        ("init", {"cli_overrides": dict(captured_overrides)}),
        ("update", "all", 8, True, (1, 103), (11,)),
        ("extract", True, True, True),
        ("mapping", True, True, True),
    ]
    assert signals.progress.calls == [
        (
            ExecutionTaskProgress(
                stage_key="update",
                stage_label="更新数据",
                entity_scope_label="英雄 + 地图",
                current=0,
                total=1,
                message="正在更新基础数据…",
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="update",
                stage_label="更新数据",
                entity_scope_label="英雄 + 地图",
                current=1,
                total=1,
                message="更新数据完成",
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="extract",
                stage_label="音频解包",
                entity_scope_label="英雄 + 地图",
                current=0,
                total=0,
                message="正在准备解包任务…",
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="extract",
                stage_label="音频解包",
                entity_scope_label="英雄",
                current=1,
                total=2,
                message="Annie 解包完成",
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="extract",
                stage_label="音频解包",
                entity_scope_label="英雄 + 地图",
                current=1,
                total=1,
                message="音频解包阶段已结束",
                stage_finished=True,
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="mapping",
                stage_label="事件映射",
                entity_scope_label="英雄 + 地图",
                current=0,
                total=0,
                message="正在准备事件映射任务…",
            ),
        ),
        (
            ExecutionTaskProgress(
                stage_key="mapping",
                stage_label="事件映射",
                entity_scope_label="地图",
                current=1,
                total=1,
                message="召唤师峡谷 映射完成",
            ),
        ),
    ]
    assert result.completed_steps == ("更新数据", "音频解包", "事件映射")
    assert result.summary.startswith("已完成：更新数据 -> 音频解包 -> 事件映射")
