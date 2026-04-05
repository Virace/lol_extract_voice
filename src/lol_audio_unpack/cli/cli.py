"""统一 CLI 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from ..app.facade import LolAudioUnpackApp
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
from .runtime import _apply_config_profile, _validate_config_argv, initialize_app, validate_args


def _detect_mode(argv0: str) -> EntryMode:
    """根据脚本名推断当前 CLI 模式。"""
    return "mapping" if Path(argv0).stem.lower() == "mapping" else "unpack"


def main() -> None:
    """统一 CLI 主入口。"""
    app_context: AppContext | None = None
    run_summary = None
    summary_sink_id: int | None = None
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

        if app_context.config.source_mode is SourceMode.REMOTE_SNAPSHOT and (
            _has_extract(args) or _has_mapping(args)
        ):
            with run_summary.stage_context("remote_workflow", label="远端实体工作流"):
                run_remote_workflow(args, app)
            if _has_wav(args):
                with run_summary.stage_context("wav", label="WAV 转码"):
                    run_wav(args, app)
            return

        if _has_update(args):
            with run_summary.stage_context("update", label="数据更新"):
                run_update(args, app)
        if _has_extract(args):
            with run_summary.stage_context("extract", label="音频解包"):
                run_extract(args, app)
        if _has_wav(args):
            with run_summary.stage_context("wav", label="WAV 转码"):
                run_wav(args, app)
        if _has_mapping(args):
            with run_summary.stage_context("mapping", label="事件映射"):
                run_mapping(args, app)
        app.cleanup_remote_artifacts()

    except KeyboardInterrupt:
        logger.warning("用户中断操作")
        sys.exit(1)
    except Exception as exc:
        _log_top_error(exc, dev_mode=bool(getattr(locals().get("args"), "dev", False)))
        sys.exit(1)
    finally:
        if summary_sink_id is not None:
            logger.remove(summary_sink_id)
        if app_context is not None and run_summary is not None:
            emit_cli_run_summary(run_summary, log_path=app_context.paths.log_path)


__all__ = ["main"]



