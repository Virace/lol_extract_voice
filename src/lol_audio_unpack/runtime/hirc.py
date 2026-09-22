"""任务级 HIRC 外部调用适配；路径由调用方快照固定。"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from league_tools import NativeHIRC, WwiserHIRC

from .tool_process import ToolError, run_tool


@dataclass(frozen=True)
class WwiserTool:
    """提供 WwiserHIRC 所需的窄接口，不使用上游自动下载单例。"""

    wwiser_path: Path
    timeout: float = 60
    cancel: Event | None = None

    def process_single_file(
        self, bnk_file: str | Path, output_file: str | Path | None = None, dump_type: str = "xml"
    ) -> Path:
        """实际执行 WWISER 并返回已产生的 dump 文件。

        Raises:
            ToolError: 路径、Python 运行环境、调用或输出不可用。
        """
        if not self.wwiser_path.is_file():
            raise ToolError("path", f"WWISER 文件不存在：{self.wwiser_path}")
        python = shutil.which("python") if getattr(sys, "frozen", False) else sys.executable
        if not python:
            raise ToolError("start", "WWISER 需要可用的 Python 解释器")
        bnk = Path(bnk_file)
        base = Path(output_file).with_suffix("") if output_file else bnk.with_suffix("")
        detail = run_tool(
            [python, str(self.wwiser_path), "-d", dump_type, "-dn", str(base), str(bnk)],
            timeout=self.timeout,
            cancel=self.cancel,
        )
        output = base.with_suffix(".txt" if dump_type == "txt" else ".xml")
        if not output.is_file() or not output.stat().st_size:
            raise ToolError("output", f"WWISER 未生成有效输出：{detail or '未返回诊断'}")
        return output


def load_hirc(
    bnk: Path, *, manager: WwiserTool | None = None, cache_dir: Path | None = None, use_cache: bool = True
) -> NativeHIRC | WwiserHIRC:
    """正式映射与样本探测共用同一 HIRC 解析入口。"""
    if manager is None:
        return NativeHIRC.from_bnk(bnk, cache_dir=cache_dir, use_cache=use_cache)
    return WwiserHIRC.from_bnk(bnk, cache_dir=cache_dir, use_cache=use_cache, wwiser_manager=manager)
