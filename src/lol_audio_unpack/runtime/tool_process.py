"""外部工具的有界调用与原始诊断，不提供下载或重试。"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Sequence
from threading import Event
from time import monotonic


class ToolError(RuntimeError):
    """保留可呈现的故障类别与工具原始诊断。"""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind


def stop_process(process: subprocess.Popen) -> None:
    """终止本次调用的进程树，并回收直接子进程。"""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_tool(args: Sequence[str], *, timeout: float, cancel: Event | None = None) -> str:
    """执行结构化参数，超时或取消时结束进程树。

    Returns:
        合并的标准输出和标准错误，供调用方记录诊断。

    Raises:
        ToolError: 启动、退出、超时或取消失败；不猜测工具内部原因。
    """
    if timeout <= 0:
        raise ValueError("工具超时必须大于零")
    if cancel is not None and cancel.is_set():
        raise ToolError("cancelled", "已取消工具调用")
    try:
        process = subprocess.Popen(
            list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise ToolError("start", f"无法启动：{exc}") from exc
    deadline = monotonic() + timeout
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise ToolError("cancelled", "已取消工具调用")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ToolError("timeout", f"工具调用超过 {timeout:g} 秒")
            try:
                output, _ = process.communicate(timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        stop_process(process)
        raise
    detail = output.decode("utf-8", errors="replace").strip()
    if process.returncode:
        raise ToolError("exit", f"工具退出码 {process.returncode}：{detail or '未返回诊断'}")
    return detail
