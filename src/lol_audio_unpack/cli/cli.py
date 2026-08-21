"""统一 CLI 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from ..app.facade import LolAudioUnpackApp
from ..app.results import ResultStatus, RunResult, StageResult
from ..app.types import AppContext, SourceMode
from ..utils.run_summary import attach_run_summary_sink, emit_cli_run_summary, get_or_create_run_summary
from .dispatch import (
    _has_extract,
    _has_mapping,
    _has_update,
    _has_wav,
    _log_top_error,
    run_extract,
    run_mapping,
    run_remote_workflow,
    run_update,
    run_wav,
)
from .parser import EntryMode, create_parser
from .runtime import CliInputError, _apply_config_profile, _validate_config_argv, initialize_app, validate_args

EXIT_CODE_BY_STATUS = {
    ResultStatus.SUCCESS: 0,
    ResultStatus.PARTIAL: 3,
    ResultStatus.FAILED: 1,
    ResultStatus.CANCELLED: 130,
}


def _detect_mode(argv0: str) -> EntryMode:
    """根据脚本名推断当前 CLI 模式。"""
    return "mapping" if Path(argv0).stem.lower() == "mapping" else "unpack"


def _latest_stage(stages: list[StageResult], stage_key: str) -> StageResult | None:
    """返回最近一次同名阶段结果。"""
    return next((stage for stage in reversed(stages) if stage.stage == stage_key), None)


def _require_stage_result(result: StageResult | None, stage_key: str) -> StageResult:
    """拒绝已选择阶段静默返回 ``None``。"""
    if result is None:
        raise RuntimeError(f"已选择的 {stage_key} 阶段没有返回执行结果")
    return result


def _require_run_result(result: RunResult | None) -> RunResult:
    """拒绝远端工作流静默返回 ``None``。"""
    if result is None:
        raise RuntimeError("远端工作流没有返回执行结果")
    return result


def _log_run_result(result: RunResult) -> None:
    """根据 typed result 输出整轮工作的唯一主结论。"""
    if result.status is ResultStatus.SUCCESS:
        logger.success(f"执行成功：已完成 {result.stage_count} 个阶段。")
        return
    if result.status is ResultStatus.PARTIAL:
        logger.warning(
            "执行部分完成：阶段 {} 个，成功实体 {} 个，部分成功 {} 个，失败 {} 个。",
            result.stage_count,
            result.success_count,
            result.partial_count,
            result.failed_count,
        )
        return
    if result.status is ResultStatus.CANCELLED:
        logger.warning("执行已取消，未开始的后续阶段已停止。")
        return
    logger.error(f"执行失败：已尝试 {result.stage_count} 个阶段。")


def main() -> int:
    """统一 CLI 主入口，并返回稳定进程退出码。"""
    app_context: AppContext | None = None
    app: LolAudioUnpackApp | None = None
    run_summary = None
    summary_sink_id: int | None = None
    stages: list[StageResult] = []
    input_failed = False
    should_log_result = True
    args = None
    try:
        mode = _detect_mode(sys.argv[0])
        parser = create_parser(mode)
        argv = sys.argv[1:]
        args = parser.parse_args(argv)
        if mode == "mapping" and not args.actions:
            args.actions = ["mapping"]

        _validate_config_argv(argv)
        _apply_config_profile(args)
        validate_args(args, parser)

        app_context = initialize_app(args)
        app = LolAudioUnpackApp(app_context)
        run_summary = get_or_create_run_summary(app_context.runtime_cache)
        summary_sink_id = attach_run_summary_sink(run_summary)

        runs_remote_workflow = app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT and (
            _has_extract(args) or _has_mapping(args)
        )
        if runs_remote_workflow:
            with run_summary.stage_context("remote_workflow", label="远端实体工作流"):
                remote_result = _require_run_result(run_remote_workflow(args, app))
            stages.extend(remote_result.stages)
            update_result = _latest_stage(stages, "update")
            extract_result = _latest_stage(stages, "extract")
            can_run_wav = (
                _has_wav(args)
                and remote_result.status is not ResultStatus.CANCELLED
                and not (update_result is not None and update_result.status is ResultStatus.FAILED)
                and not (
                    _has_extract(args) and extract_result is not None and extract_result.status is ResultStatus.FAILED
                )
            )
            if can_run_wav:
                with run_summary.stage_context("wav", label="WAV 转码"):
                    wav_result = _require_stage_result(
                        run_wav(args, app, extract_result=extract_result),
                        "wav",
                    )
                stages.append(wav_result)

        continue_after_update = not runs_remote_workflow
        if not runs_remote_workflow and _has_update(args):
            with run_summary.stage_context("update", label="数据更新"):
                update_result = _require_stage_result(run_update(args, app), "update")
            stages.append(update_result)
            continue_after_update = update_result.status not in {
                ResultStatus.FAILED,
                ResultStatus.CANCELLED,
            }

        extract_result: StageResult | None = None
        continue_after_cancel = continue_after_update
        if continue_after_update and _has_extract(args):
            with run_summary.stage_context("extract", label="音频解包"):
                extract_result = _require_stage_result(run_extract(args, app), "extract")
            stages.append(extract_result)
            continue_after_cancel = extract_result.status is not ResultStatus.CANCELLED

        can_run_wav = (
            continue_after_update
            and continue_after_cancel
            and _has_wav(args)
            and not (extract_result is not None and extract_result.status is ResultStatus.FAILED)
        )
        if can_run_wav:
            with run_summary.stage_context("wav", label="WAV 转码"):
                wav_result = _require_stage_result(
                    run_wav(args, app, extract_result=extract_result),
                    "wav",
                )
            stages.append(wav_result)
            continue_after_cancel = wav_result.status is not ResultStatus.CANCELLED

        if continue_after_update and continue_after_cancel and _has_mapping(args):
            with run_summary.stage_context("mapping", label="事件映射"):
                mapping_result = _require_stage_result(run_mapping(args, app), "mapping")
            stages.append(mapping_result)

    except CliInputError:
        input_failed = True
        should_log_result = False
    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        current_stage = getattr(run_summary, "current_stage", None) or "run"
        stages.append(StageResult.cancelled(current_stage, note="用户中断操作。"))
    except Exception as exc:
        _log_top_error(exc, dev_mode=bool(getattr(args, "dev", False)))
        # 意外异常表示整轮运行不可信；不能因之前已有成功阶段而降级成 partial。
        stages = [StageResult.from_error("run", exc)]
    finally:
        if app is not None:
            try:
                app.cleanup_remote_artifacts()
            except Exception as cleanup_error:  # noqa: BLE001
                logger.error("远端准备产物清理失败；原执行结果已保留。")
                stages.append(StageResult.from_error("cleanup", cleanup_error))
        if summary_sink_id is not None:
            logger.remove(summary_sink_id)
        if app_context is not None and run_summary is not None:
            emit_cli_run_summary(run_summary, log_path=app_context.paths.log_path)

    if input_failed:
        return 2

    result = RunResult(tuple(stages))
    if should_log_result:
        _log_run_result(result)
    return EXIT_CODE_BY_STATUS[result.status]


__all__ = ["main"]
