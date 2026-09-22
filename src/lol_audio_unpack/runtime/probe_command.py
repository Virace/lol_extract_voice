"""发布包的无界面工具自检入口，复用正式样本与后端调用。"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from threading import Event, Timer
from time import monotonic

from ..app.types import WavOutputOptions
from .probe import probe_tool


def check_tools(argv: list[str]) -> int:
    """按显式命令自检内置及指定外部工具，写出完整诊断报告并返回退出码。"""
    parser = argparse.ArgumentParser(description="无界面验证发布包内的实际工具能力")
    parser.add_argument("--check-tools", type=Path, required=True, metavar="REPORT")
    parser.add_argument("--wwiser-path")
    parser.add_argument("--vgmstream-path")
    parser.add_argument("--check-cancel", action="store_true")
    args = parser.parse_args(argv)
    report = args.check_tools.resolve()
    cases = [("hirc", None), ("wav", None)]
    if args.wwiser_path:
        cases.append(("hirc", str(Path(args.wwiser_path).resolve())))
    if args.vgmstream_path:
        cases.append(("wav", str(Path(args.vgmstream_path).resolve())))
    results = []
    for tool, path in cases:
        started = monotonic()
        result = probe_tool(
            tool, path=path, options=WavOutputOptions(timeout_seconds=15), scratch_root=report.parent / "probes"
        )
        results.append({**asdict(result), "seconds": monotonic() - started})
    cancelled = None
    if args.check_cancel:
        cancel = Event()
        timer = Timer(0.2, cancel.set)
        timer.start()
        try:
            cancelled = asdict(probe_tool("wav", scratch_root=report.parent / "probes", cancel=cancel))
        finally:
            timer.cancel()
    payload = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "package": str(files("lol_audio_unpack")),
        "results": results,
        "cancel": cancelled,
        "children": [child.pid for child in multiprocessing.active_children()],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = all(result["kind"] == "ok" for result in results)
    if args.check_cancel:
        passed = passed and cancelled["kind"] == "cancelled" and not payload["children"]
    return 0 if passed else 1
