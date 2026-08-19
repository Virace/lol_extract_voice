#!/usr/bin/env python3
"""真实链路基准脚本（更新 -> 解包）。

支持三类场景：
1. `single_vo`：更新后仅解包单个英雄（VO-only）。
2. `targeted`：按显式英雄或地图 ID 更新并解包。
3. `full_extract`：更新后执行全量解包（英雄 + 地图，默认全类型）。

支持两种执行引擎：
1. `cli`：通过命令行子进程执行，模拟真实用户调用。
2. `api`：直接调用 Python API，便于排查编排层问题。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import msgpack
from loguru import logger
from ruamel.yaml import YAML

from lol_audio_unpack.app.context import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.types import OperationOptions

CHAMPION_ID_POOL: tuple[str, ...] = (
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "48",
    "50",
    "51",
    "53",
    "54",
    "55",
    "56",
    "57",
    "58",
    "59",
    "60",
    "61",
    "62",
    "63",
    "64",
    "67",
    "68",
    "69",
    "72",
    "74",
    "75",
    "76",
    "77",
    "78",
    "79",
    "80",
    "81",
    "82",
    "83",
    "84",
    "85",
    "86",
    "89",
    "90",
    "91",
    "92",
    "96",
    "98",
    "99",
    "101",
    "102",
    "103",
    "104",
    "105",
    "106",
    "107",
    "110",
    "111",
    "112",
    "113",
    "114",
    "115",
    "117",
    "119",
    "120",
    "121",
    "122",
    "126",
    "127",
    "131",
    "133",
    "134",
    "136",
    "141",
    "142",
    "143",
    "145",
    "147",
    "150",
    "154",
    "157",
    "161",
    "163",
    "164",
    "166",
    "200",
    "201",
    "202",
    "203",
    "221",
    "222",
    "223",
    "233",
    "234",
    "235",
    "236",
    "238",
    "240",
    "245",
    "246",
    "254",
    "266",
    "267",
    "268",
    "350",
    "360",
    "412",
    "420",
    "421",
    "427",
    "429",
    "432",
    "497",
    "498",
    "516",
    "517",
    "518",
    "523",
    "526",
    "555",
    "711",
    "777",
    "799",
    "800",
    "804",
    "875",
    "876",
    "887",
    "888",
    "893",
    "895",
    "897",
    "901",
    "902",
    "904",
    "910",
    "950",
)

RESOURCE_INDEX_FIELDS: tuple[str, ...] = (
    "candidateWads",
    "cacheHits",
    "cacheMisses",
    "uniqueTocLoads",
    "duplicatePhysicalWadLoads",
    "tocSeconds",
)
RESOURCE_SCHEMA_V2 = 2
RSS_SAMPLE_INTERVAL_SECONDS = 0.05
_TH32CS_SNAPPROCESS = 0x00000002
_MAX_PATH = 260


@dataclass(frozen=True)
class BenchmarkSource:
    """基准运行的源码树标识。"""

    root: Path
    label: str


@dataclass(frozen=True)
class BenchmarkContext:
    """基准脚本运行上下文。"""

    repo_root: Path
    runner: str
    uv_entry: str
    timeout: int
    workers: int
    log_level: str
    run_id: str
    source: BenchmarkSource


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="执行更新 -> 解包真实链路基准测试")
    parser.add_argument(
        "--mode",
        choices=["single_vo", "targeted", "full_extract", "both"],
        default="both",
        help="执行模式：single_vo / targeted / full_extract / both",
    )
    parser.add_argument(
        "--runner",
        choices=["cli", "api", "both"],
        default="cli",
        help="执行引擎：cli / api / both",
    )
    parser.add_argument(
        "--single-vo-id",
        type=str,
        default=None,
        help="single_vo 模式指定英雄 ID，不传则从 manifest 自动选择",
    )
    parser.add_argument(
        "--target-champions",
        type=str,
        default=None,
        help="targeted 模式的显式英雄 ID，使用逗号分隔",
    )
    parser.add_argument(
        "--target-maps",
        type=str,
        default=None,
        help="targeted 模式的显式地图 ID，使用逗号分隔；更新时自动补充地图 0",
    )
    parser.add_argument(
        "--targeted-exclude-type",
        type=str,
        default="",
        help="targeted 模式 EXCLUDE_TYPE，默认空字符串表示全类型",
    )
    parser.add_argument(
        "--max-workers",
        default="auto",
        help="worker 数，默认 auto（使用 os.cpu_count()）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".temp/benchmarks/latest.json"),
        help="基准结果输出路径（JSON）",
    )
    parser.add_argument(
        "--uv-entry",
        default="python",
        help="子进程入口，默认 python（由外层 uv run 提供环境）",
    )
    parser.add_argument(
        "--game-path",
        type=Path,
        default=None,
        help="游戏目录（必填）",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="输出目录根（必填）",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="CLI 子进程加载的源码树根目录，默认当前仓库",
    )
    parser.add_argument(
        "--source-label",
        type=str,
        default="current",
        help="写入报告的源码标签，默认 current",
    )
    parser.add_argument(
        "--prepare-update",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在解包前执行 update 动作（默认开启）",
    )
    parser.add_argument(
        "--skip-events",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="更新阶段是否跳过事件处理（默认不跳过）",
    )
    parser.add_argument(
        "--with-bp-vo",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="显式覆盖 WITH_BP_VO（未设置则沿用默认配置）",
    )
    parser.add_argument(
        "--single-vo-exclude-type",
        type=str,
        default="SFX,MUSIC",
        help="single_vo 模式 EXCLUDE_TYPE，默认仅保留 VO（SFX,MUSIC）",
    )
    parser.add_argument(
        "--full-extract-exclude-type",
        type=str,
        default="",
        help="full_extract 模式 EXCLUDE_TYPE，默认空字符串表示全类型",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="CLI 子命令超时秒数",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="执行日志级别",
    )
    parser.add_argument(
        "--enable-league-tools-log",
        action="store_true",
        help="启用 league_tools 日志（默认关闭，避免超大量输出）",
    )
    return parser.parse_args()


def resolve_workers(raw_workers: str) -> int:
    """解析并归一化 worker 参数。

    Args:
        raw_workers: 命令行输入值，支持 `auto` 或正整数。

    Returns:
        实际 worker 数。

    Raises:
        ValueError: 输入不是合法值时抛出。
    """
    if raw_workers == "auto":
        return max(1, os.cpu_count() or 1)
    try:
        value = int(raw_workers)
    except ValueError as e:
        raise ValueError(f"max_workers 非法: {raw_workers}") from e
    return max(1, value)


def read_file_tail(path: Path, *, max_chars: int = 1200) -> str:
    """读取文本文件尾部内容。"""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def build_source_env(source: BenchmarkSource) -> dict[str, str]:
    """构建让 CLI 子进程优先导入指定源码树的环境变量。

    Args:
        source: 当前比较对象的源码树标识。

    Returns:
        含有首位 ``<source-root>/src`` 的子进程环境变量。
    """
    env = os.environ.copy()
    source_path = str(source.root / "src")
    current_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = source_path if not current_path else f"{source_path}{os.pathsep}{current_path}"
    return env


def _source_runner_error(runner: str, source: BenchmarkSource, repo_root: Path) -> str | None:
    if runner in {"api", "both"} and source.root != repo_root.resolve():
        return "--source-root 仅支持 --runner cli；API runner 始终使用当前进程源码"
    return None


def _read_windows_process_rss_bytes(pid: int) -> int | None:
    """读取单个 Windows 进程当前工作集大小。"""

    class ProcessMemoryCountersEx(ctypes.Structure):
        """映射 Windows `PROCESS_MEMORY_COUNTERS_EX` 结构。"""

        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
            ("private_usage", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCountersEx),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        access = 0x0400 | 0x0010  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        handle = kernel32.OpenProcess(access, False, pid)
        if not handle:
            return None
        try:
            counters = ProcessMemoryCountersEx()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            return int(counters.working_set_size)
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        return None


class _ProcessEntry32W(ctypes.Structure):
    """映射 Windows `PROCESSENTRY32W` 结构。"""

    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * _MAX_PATH),
    ]


def _read_windows_process_parents() -> dict[int, int]:
    """读取 Windows 当前进程表中的 PID → parent PID 映射。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            return {}
        try:
            entry = _ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                return {}
            parents: dict[int, int] = {}
            while True:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
            return parents
        finally:
            kernel32.CloseHandle(snapshot)
    except OSError:
        return {}


def collect_process_tree_pids(root_pid: int, parents: dict[int, int]) -> set[int]:
    """从 parent 映射收集根进程及全部后代 PID。

    Args:
        root_pid: 基准命令根进程 PID。
        parents: PID 到 parent PID 的快照。

    Returns:
        包含根进程与递归后代的 PID 集合。
    """
    tree = {root_pid}
    while True:
        descendants = {pid for pid, parent_pid in parents.items() if parent_pid in tree}
        expanded = tree | descendants
        if expanded == tree:
            return tree
        tree = expanded


def read_process_rss_bytes(pid: int) -> int | None:
    """读取可移植范围内的当前进程 RSS。

    Windows 通过 `GetProcessMemoryInfo` 获取工作集，Linux 读取 `/proc`。其他系统或进程
    已退出导致无法读取时返回 ``None``，由调用方明确标为 unavailable。

    Args:
        pid: 要采样的子进程 PID。

    Returns:
        当前 RSS 字节数；不可用时返回 ``None``。
    """
    if os.name == "nt":
        pids = collect_process_tree_pids(pid, _read_windows_process_parents())
        samples = [value for process_pid in pids if (value := _read_windows_process_rss_bytes(process_pid)) is not None]
        return sum(samples) if samples else None

    status_file = Path("/proc") / str(pid) / "status"
    try:
        for line in status_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def wait_for_command(proc: subprocess.Popen[Any], timeout: int) -> int | None:
    """等待命令完成，并周期采样子进程 RSS 峰值。

    Args:
        proc: 已启动的 CLI 子进程。
        timeout: 最大等待秒数。

    Returns:
        采样到的 RSS 峰值字节数；当前平台不能读取时返回 ``None``。

    Raises:
        subprocess.TimeoutExpired: 子进程超过超时时间时抛出。
    """
    deadline = time.monotonic() + timeout
    peak_rss_bytes: int | None = None
    while proc.poll() is None:
        rss_bytes = read_process_rss_bytes(proc.pid)
        if rss_bytes is not None:
            peak_rss_bytes = max(peak_rss_bytes or 0, rss_bytes)
        if time.monotonic() >= deadline:
            proc.kill()
            proc.wait()
            raise subprocess.TimeoutExpired(proc.args, timeout)
        time.sleep(RSS_SAMPLE_INTERVAL_SECONDS)

    rss_bytes = read_process_rss_bytes(proc.pid)
    if rss_bytes is not None:
        peak_rss_bytes = max(peak_rss_bytes or 0, rss_bytes)
    return peak_rss_bytes


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int,
    *,
    env: dict[str, str] | None = None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    """执行子进程命令并返回结构化结果与 RSS 采样峰值。"""
    start = time.perf_counter()
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log_file is None:
            capture_dir = cwd / ".temp"
            capture_dir.mkdir(parents=True, exist_ok=True)
            with (
                tempfile.TemporaryFile(mode="w+t", encoding="utf-8", dir=capture_dir) as stdout_sink,
                tempfile.TemporaryFile(mode="w+t", encoding="utf-8", dir=capture_dir) as stderr_sink,
            ):
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    env=env,
                    stdout=stdout_sink,
                    stderr=stderr_sink,
                    text=True,
                )
                peak_rss_bytes = wait_for_command(proc, timeout)
                stdout_sink.seek(0)
                stderr_sink.seek(0)
                stdout_tail = stdout_sink.read()[-1200:]
                stderr_tail = stderr_sink.read()[-1200:]
        else:
            with log_file.open("a", encoding="utf-8") as sink:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(cwd),
                    env=env,
                    stdout=sink,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                peak_rss_bytes = wait_for_command(proc, timeout)
            stdout_tail = read_file_tail(log_file)
            stderr_tail = ""

        elapsed = round(time.perf_counter() - start, 3)
        result: dict[str, Any] = {
            "status": "ok" if proc.returncode == 0 else "fail",
            "returncode": proc.returncode,
            "elapsed_sec": elapsed,
            "peak_rss_bytes": peak_rss_bytes,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }
        if log_file is not None:
            result["log_file"] = str(log_file)
        return result
    except subprocess.TimeoutExpired:
        elapsed = round(time.perf_counter() - start, 3)
        result = {
            "status": "timeout",
            "returncode": None,
            "elapsed_sec": elapsed,
            "stdout_tail": read_file_tail(log_file) if log_file is not None else "",
            "stderr_tail": f"命令超时({timeout}s)",
        }
        if log_file is not None:
            result["log_file"] = str(log_file)
        return result


def get_game_version(game_path: Path) -> str:
    """读取并解析游戏版本号。"""
    meta = game_path / "Game" / "content-metadata.json"
    if not meta.is_file():
        raise FileNotFoundError(f"缺少版本文件: {meta}")
    raw = json.loads(meta.read_text(encoding="utf-8"))
    version_str = str(raw.get("version", ""))
    match = re.match(r"^(\d+\.\d+)\.", version_str)
    if not match:
        raise ValueError(f"无法解析版本号: {version_str}")
    return match.group(1)


def find_manifest_data_file(output_path: Path, version: str) -> Path | None:
    """定位目标版本 manifest 的 data 文件。"""
    base = output_path / "manifest" / version / "data"
    return find_data_file(base)


def find_data_file(base: Path) -> Path | None:
    """定位 msgpack、YAML 或 JSON 格式的数据文件。

    Args:
        base: 不带格式后缀的数据文件基路径。

    Returns:
        找到的数据文件；所有格式均不存在时返回 ``None``。
    """
    for suffix in (".msgpack", ".yml", ".json"):
        candidate = base.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def load_manifest_data(path: Path) -> dict[str, Any]:
    """按后缀读取 manifest data。"""
    if path.suffix == ".msgpack":
        return msgpack.unpackb(path.read_bytes(), raw=False)
    if path.suffix in {".yml", ".yaml"}:
        yaml = YAML(typ="safe")
        data = yaml.load(path.read_text(encoding="utf-8"))
        return data or {}
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"不支持的 data 文件格式: {path}")


def add_result(  # noqa: PLR0913
    results: list[dict[str, Any]],
    *,
    runner: str,
    scenario: str,
    step: str,
    output_root: Path,
    command: str | None,
    data: dict[str, Any],
) -> None:
    """追加单条结果记录。"""
    row = {
        "runner": runner,
        "scenario": scenario,
        "step": step,
        "output_root": str(output_root),
        "command": command or "",
    }
    row.update(data)
    results.append(row)


def snapshot_wem_metrics(output_root: Path) -> dict[str, int]:
    """统计当前输出目录中的 wem 文件数量与大小。"""
    audio_root = output_root / "audios"
    if not audio_root.exists():
        return {"wem_files": 0, "wem_bytes": 0}
    file_count = 0
    total_bytes = 0
    for wem_file in audio_root.rglob("*.wem"):
        if wem_file.is_file():
            file_count += 1
            total_bytes += wem_file.stat().st_size
    return {"wem_files": file_count, "wem_bytes": total_bytes}


def build_metric_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    """构建指标增量。"""
    return {
        "wem_files_before": before["wem_files"],
        "wem_files_after": after["wem_files"],
        "wem_files_delta": after["wem_files"] - before["wem_files"],
        "wem_bytes_before": before["wem_bytes"],
        "wem_bytes_after": after["wem_bytes"],
        "wem_bytes_delta": after["wem_bytes"] - before["wem_bytes"],
    }


def parse_target_ids(raw_ids: str | None, *, option_name: str) -> tuple[str, ...]:
    """解析 targeted 模式的逗号分隔数值 ID。

    Args:
        raw_ids: 命令行传入的原始 ID 字符串。
        option_name: 用于错误消息的参数名。

    Returns:
        去重且保持输入顺序的 ID 元组。

    Raises:
        ValueError: ID 为空、非数值或重复提供分隔符时抛出。
    """
    if raw_ids is None:
        return ()
    parts = tuple(part.strip() for part in raw_ids.split(","))
    if not parts or any(not part or not part.isdecimal() for part in parts):
        raise ValueError(f"{option_name} 必须是一个或多个逗号分隔的数值 ID")
    return tuple(dict.fromkeys(parts))


def with_common_map(map_ids: tuple[str, ...]) -> tuple[str, ...]:
    """为地图更新补充公共地图 0，维持既有去重前置条件。"""
    if not map_ids or "0" in map_ids:
        return map_ids
    return ("0", *map_ids)


def pick_single_vo_champion_id(manifest_data: dict[str, Any], preferred_id: str | None) -> str:
    """从 manifest 中确定 single_vo 目标英雄 ID。

    Args:
        manifest_data: 当前版本 data 文件内容。
        preferred_id: 用户显式指定 ID。

    Returns:
        可用英雄 ID 字符串。

    Raises:
        ValueError: 无可用英雄 ID 时抛出。
    """
    champions = manifest_data.get("champions") or {}
    champion_ids = sorted((str(champ_id) for champ_id in champions.keys()), key=int)
    if preferred_id:
        if preferred_id not in champion_ids:
            raise ValueError(f"指定 single_vo 英雄ID不存在于当前版本: {preferred_id}")
        return preferred_id

    available_set = set(champion_ids)
    for candidate in CHAMPION_ID_POOL:
        if candidate in available_set:
            return candidate
    if champion_ids:
        return champion_ids[0]
    raise ValueError("当前 manifest 不包含任何英雄数据，无法执行 single_vo")


def build_base_command(ctx: BenchmarkContext) -> list[str]:
    """构建 CLI 基础命令前缀。

    约定：
    - `--uv-entry uv`（默认）：使用 `uv run python -m ...`。
    - `--uv-entry python`：使用当前解释器 `sys.executable -m ...`，避免嵌套 `uv run`。
    """
    if ctx.uv_entry == "python":
        return [sys.executable, "-m", "lol_audio_unpack"]
    return [ctx.uv_entry, "run", "python", "-m", "lol_audio_unpack"]


def append_bool_flag(cmd: list[str], flag: str, value: bool | None) -> None:
    """按值追加 bool 可选参数。"""
    if value is None:
        return
    cmd.append(flag if value else f"--no-{flag.removeprefix('--')}")


def build_update_command(  # noqa: PLR0913
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    skip_events: bool,
    with_bp_vo: bool | None,
    champion_ids: tuple[str, ...] = (),
    map_ids: tuple[str, ...] = (),
) -> list[str]:
    """构建更新命令，可选地限制为显式英雄或地图目标。"""
    cmd = build_base_command(ctx)
    cmd.extend(
        [
            "update",
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
        ]
    )
    if champion_ids:
        cmd.extend(["--champions", ",".join(champion_ids)])
    if map_ids:
        cmd.extend(["--maps", ",".join(map_ids)])
    if skip_events:
        cmd.append("--skip-events")
    append_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def build_single_vo_command(  # noqa: PLR0913
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    champion_id: str,
    exclude_type: str,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建 single_vo 解包命令。"""
    cmd = build_base_command(ctx)
    cmd.extend(
        [
            "extract",
            "--champions",
            champion_id,
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
            "--exclude-type",
            exclude_type,
        ]
    )
    append_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def build_full_extract_command(
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    exclude_type: str,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建全量解包命令。"""
    cmd = build_base_command(ctx)
    cmd.extend(
        [
            "extract",
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
            "--exclude-type",
            exclude_type,
        ]
    )
    append_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def build_targeted_extract_command(  # noqa: PLR0913
    ctx: BenchmarkContext,
    game_path: Path,
    output_path: Path,
    *,
    champion_ids: tuple[str, ...] = (),
    map_ids: tuple[str, ...] = (),
    exclude_type: str,
    with_bp_vo: bool | None,
) -> list[str]:
    """构建显式英雄或地图范围的解包命令。

    Args:
        ctx: 基准运行上下文。
        game_path: 本地游戏目录。
        output_path: 当前场景的输出目录。
        champion_ids: 要解包的英雄 ID。
        map_ids: 要解包的地图 ID。
        exclude_type: 传给 CLI 的音频类型排除值。
        with_bp_vo: BP VO 覆盖值。

    Returns:
        可直接交给子进程执行的 CLI 参数列表。

    Raises:
        ValueError: 未指定任何英雄或地图目标时抛出。
    """
    if not champion_ids and not map_ids:
        raise ValueError("targeted extract 至少需要一个英雄或地图 ID")

    cmd = build_base_command(ctx)
    cmd.extend(
        [
            "extract",
            "--max-workers",
            str(ctx.workers),
            "--log-level",
            ctx.log_level,
            "--game-path",
            str(game_path),
            "--output-path",
            str(output_path),
            "--exclude-type",
            exclude_type,
        ]
    )
    if champion_ids:
        cmd.extend(["--champions", ",".join(champion_ids)])
    if map_ids:
        cmd.extend(["--maps", ",".join(map_ids)])
    append_bool_flag(cmd, "--with-bp-vo", with_bp_vo)
    return cmd


def run_cli_step(
    ctx: BenchmarkContext,
    *,
    cmd: list[str],
    output_root: Path,
    step_name: str,
) -> dict[str, Any]:
    """执行单个 CLI 步骤，并附带 wem 指标增量。"""
    before = snapshot_wem_metrics(output_root)
    log_file = output_root / "reports" / f"benchmark_{ctx.runner}_{step_name}.log"
    result = run_command(
        cmd=cmd,
        cwd=ctx.source.root,
        timeout=ctx.timeout,
        env=build_source_env(ctx.source),
        log_file=log_file,
    )
    after = snapshot_wem_metrics(output_root)
    result.update(build_metric_delta(before, after))
    return result


def run_api_step(output_root: Path, handler: Any) -> dict[str, Any]:
    """执行单个 API 步骤，并附带 wem 指标增量。"""
    before = snapshot_wem_metrics(output_root)
    start = time.perf_counter()
    try:
        handler()
        status = "ok"
        error: str | None = None
        trace_tail = ""
    except Exception as e:  # noqa: BLE001
        status = "fail"
        error = f"{type(e).__name__}: {e}"
        trace_tail = traceback.format_exc()[-1200:]
    elapsed = round(time.perf_counter() - start, 3)
    after = snapshot_wem_metrics(output_root)

    payload: dict[str, Any] = {
        "status": status,
        "elapsed_sec": elapsed,
        **build_metric_delta(before, after),
    }
    if error:
        payload["error"] = error
        payload["traceback_tail"] = trace_tail
    return payload


def create_api_app(
    *,
    game_path: Path,
    output_path: Path,
    exclude_type: str,
    with_bp_vo: bool | None,
    log_level: str,
) -> Any:
    """创建 API 运行时 app 实例。"""
    settings: dict[str, Any] = {
        "GAME_PATH": str(game_path),
        "OUTPUT_PATH": str(output_path),
        "EXCLUDE_TYPE": exclude_type,
    }
    if with_bp_vo is not None:
        settings["WITH_BP_VO"] = with_bp_vo

    _ = log_level
    app_context = create_app_context(dev_mode=False, settings=settings)
    return LolAudioUnpackApp(app_context)


def run_update_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    skip_events: bool,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
    champion_ids: tuple[str, ...] = (),
    map_ids: tuple[str, ...] = (),
) -> None:
    """执行 API 更新步骤，可选地限制为显式目标。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(
        max_workers=workers,
        process_events=not skip_events,
        champion_ids=tuple(int(champion_id) for champion_id in champion_ids) or None,
        map_ids=tuple(int(map_id) for map_id in map_ids) or None,
    )
    app.update(options, target="all")


def run_single_vo_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    champion_id: str,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API single_vo 解包步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(max_workers=workers, champion_ids=(int(champion_id),))
    app.extract(options, include_maps=False)


def run_full_extract_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API 全量解包步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(max_workers=workers)
    app.extract(options)


def run_targeted_extract_api(  # noqa: PLR0913
    *,
    game_path: Path,
    output_path: Path,
    champion_ids: tuple[str, ...],
    map_ids: tuple[str, ...],
    with_bp_vo: bool | None,
    log_level: str,
    workers: int,
    exclude_type: str,
) -> None:
    """执行 API 显式目标解包步骤。"""
    app = create_api_app(
        game_path=game_path,
        output_path=output_path,
        exclude_type=exclude_type,
        with_bp_vo=with_bp_vo,
        log_level=log_level,
    )
    options = OperationOptions(
        max_workers=workers,
        champion_ids=tuple(int(champion_id) for champion_id in champion_ids),
        map_ids=tuple(int(map_id) for map_id in map_ids),
    )
    app.extract(options, include_champions=bool(champion_ids), include_maps=bool(map_ids))


def summarize_resource_index(
    output_root: Path,
    version: str,
    *,
    champion_ids: tuple[str, ...] = (),
    map_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """从 local resource schema v2 banks artifact 汇总 WAD 索引指标。

    每个 artifact 保存的是同一 update 进程中的累计快照，因此采用各字段的最大快照而不是
    跨实体求和。旧 v1 artifact 不包含 resource schema 或 diagnostics.index，会明确标记为
    unavailable，避免把缺失数据误报成零。

    Args:
        output_root: 当前基准场景输出目录。
        version: 当前游戏版本。
        champion_ids: 要读取的英雄 banks artifact ID。
        map_ids: 要读取的地图 banks artifact ID。

    Returns:
        指标可用性、聚合结果与逐实体读取状态。
    """
    entities: list[dict[str, Any]] = []
    values: dict[str, list[int | float]] = {}
    requested = (("champion", champion_ids), ("map", map_ids))

    for entity_type, entity_ids in requested:
        artifact_dir = f"{entity_type}s"
        for entity_id in entity_ids:
            base = output_root / "manifest" / version / "banks" / artifact_dir / entity_id
            artifact_file = find_data_file(base)
            entity: dict[str, Any] = {"entity_type": entity_type, "entity_id": entity_id}
            if artifact_file is None:
                entities.append({**entity, "status": "unavailable", "reason": "banks artifact 不存在"})
                continue

            try:
                payload = load_manifest_data(artifact_file)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                entities.append({**entity, "status": "unavailable", "reason": f"无法读取 banks artifact: {e}"})
                continue

            diagnostics = payload.get("diagnostics")
            index = diagnostics.get("index") if isinstance(diagnostics, dict) else None
            if payload.get("resourceSchemaVersion") != RESOURCE_SCHEMA_V2 or not isinstance(index, dict) or not index:
                entities.append(
                    {
                        **entity,
                        "status": "unavailable",
                        "reason": "banks artifact 未提供 resource schema v2 diagnostics.index",
                    }
                )
                continue

            metrics = {
                key: value
                for key, value in index.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            if not metrics:
                entities.append({**entity, "status": "unavailable", "reason": "diagnostics.index 没有数值指标"})
                continue
            entities.append({**entity, "status": "available", "index": metrics})
            for key, value in metrics.items():
                values.setdefault(key, []).append(value)

    unavailable = [entity for entity in entities if entity["status"] != "available"]
    summary: dict[str, Any] = {
        "status": "available" if values and not unavailable else "partial" if values else "unavailable",
        "aggregation": "max_cumulative_snapshot",
        "entities": entities,
        "unavailable_entities": unavailable,
    }
    for field in RESOURCE_INDEX_FIELDS:
        summary[field] = max(values[field]) if field in values else None
    for field, field_values in sorted(values.items()):
        summary.setdefault(field, max(field_values))
    return summary


def build_scenario_summary(
    rows: list[dict[str, Any]],
    *,
    runner: str,
    scenario: str,
    output_root: Path,
    source: BenchmarkSource,
) -> dict[str, Any]:
    """聚合一个场景的阶段耗时、WEM 产物和 RSS 峰值。

    Args:
        rows: 当前场景产生的原始阶段记录。
        runner: 执行引擎名称。
        scenario: 场景名称。
        output_root: 当前场景输出目录。
        source: 当前比较对象的源码树标识。

    Returns:
        适用于 baseline/current 比较的场景汇总行。
    """
    steps = {str(row.get("step")): row for row in rows if row.get("scenario") == scenario}
    update = steps.get("update")
    extract = steps.get("extract")
    elapsed = [
        float(row["elapsed_sec"])
        for row in (update, extract)
        if row is not None and isinstance(row.get("elapsed_sec"), (int, float))
    ]
    peaks = [
        int(row["peak_rss_bytes"])
        for row in (update, extract)
        if row is not None
        and isinstance(row.get("peak_rss_bytes"), int)
        and not isinstance(row.get("peak_rss_bytes"), bool)
    ]
    statuses = {str(row.get("status")) for row in steps.values()}
    if "fail" in statuses:
        status = "fail"
    elif "timeout" in statuses:
        status = "timeout"
    elif statuses == {"ok"}:
        status = "ok"
    else:
        status = "unavailable"

    return {
        "runner": runner,
        "scenario": scenario,
        "status": status,
        "output_root": str(output_root),
        "source_label": source.label,
        "source_root": str(source.root),
        "update_elapsed_sec": update.get("elapsed_sec") if update else None,
        "extract_elapsed_sec": extract.get("elapsed_sec") if extract else None,
        "end_to_end_elapsed_sec": round(sum(elapsed), 3) if elapsed else None,
        "wem_files": extract.get("wem_files_after") if extract else None,
        "wem_bytes": extract.get("wem_bytes_after") if extract else None,
        "peak_rss_bytes": max(peaks) if peaks else None,
    }


def build_targeted_summary(  # noqa: PLR0913
    rows: list[dict[str, Any]],
    *,
    runner: str,
    scenario: str,
    output_root: Path,
    source: BenchmarkSource,
    game_version: str,
    champion_ids: tuple[str, ...] = (),
    map_ids: tuple[str, ...] = (),
    diagnostic_map_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """构建带 local v2 WAD-index 诊断的 targeted 场景汇总。

    Args:
        rows: 当前场景的原始阶段记录。
        runner: 执行引擎名称。
        scenario: 场景名称。
        output_root: 当前场景输出目录。
        source: 当前比较对象的源码树标识。
        game_version: 当前游戏版本。
        champion_ids: 实际解包的英雄 ID。
        map_ids: 实际解包的地图 ID。
        diagnostic_map_ids: 读取 diagnostics 时包含的地图 ID；地图场景应含公共地图 0。

    Returns:
        包含显式目标和 resource index 快照的场景汇总。
    """
    summary = build_scenario_summary(
        rows,
        runner=runner,
        scenario=scenario,
        output_root=output_root,
        source=source,
    )
    summary["targets"] = {"champion_ids": list(champion_ids), "map_ids": list(map_ids)}
    summary["resource_index"] = summarize_resource_index(
        output_root,
        game_version,
        champion_ids=champion_ids,
        map_ids=diagnostic_map_ids or map_ids,
    )
    return summary


def run_single_vo_scenario(
    ctx: BenchmarkContext,
    args: argparse.Namespace,
    *,
    game_path: Path,
    scenario_output: Path,
    results: list[dict[str, Any]],
) -> None:
    """执行 single_vo 场景（更新 -> 单英雄 VO 解包）。"""
    scenario_output.mkdir(parents=True, exist_ok=True)
    exclude_type = args.single_vo_exclude_type

    if args.prepare_update:
        if ctx.runner == "cli":
            update_cmd = build_update_command(
                ctx,
                game_path,
                scenario_output,
                skip_events=args.skip_events,
                with_bp_vo=args.with_bp_vo,
            )
            update_result = run_cli_step(ctx, cmd=update_cmd, output_root=scenario_output, step_name="single_vo_update")
            add_result(
                results,
                runner=ctx.runner,
                scenario="single_vo",
                step="update",
                output_root=scenario_output,
                command=" ".join(update_cmd),
                data=update_result,
            )
        else:
            update_result = run_api_step(
                scenario_output,
                lambda: run_update_api(
                    game_path=game_path,
                    output_path=scenario_output,
                    skip_events=args.skip_events,
                    with_bp_vo=args.with_bp_vo,
                    log_level=ctx.log_level,
                    workers=ctx.workers,
                    exclude_type=exclude_type,
                ),
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="single_vo",
                step="update",
                output_root=scenario_output,
                command="api:update(target=all)",
                data=update_result,
            )
        if update_result.get("status") != "ok":
            return

    try:
        version = get_game_version(game_path)
        data_file = find_manifest_data_file(scenario_output, version)
        if data_file is None:
            raise FileNotFoundError(f"未找到 manifest data: {scenario_output / 'manifest' / version / 'data.*'}")
        manifest_data = load_manifest_data(data_file)
        champion_id = pick_single_vo_champion_id(manifest_data, args.single_vo_id)
    except Exception as e:  # noqa: BLE001
        add_result(
            results,
            runner=ctx.runner,
            scenario="single_vo",
            step="precheck",
            output_root=scenario_output,
            command="",
            data={"status": "fail", "error": f"{type(e).__name__}: {e}"},
        )
        return

    if ctx.runner == "cli":
        extract_cmd = build_single_vo_command(
            ctx,
            game_path,
            scenario_output,
            champion_id=champion_id,
            exclude_type=exclude_type,
            with_bp_vo=args.with_bp_vo,
        )
        extract_result = run_cli_step(
            ctx,
            cmd=extract_cmd,
            output_root=scenario_output,
            step_name="single_vo_extract",
        )
        add_result(
            results,
            runner=ctx.runner,
            scenario="single_vo",
            step="extract",
            output_root=scenario_output,
            command=" ".join(extract_cmd),
            data={**extract_result, "champion_id": champion_id},
        )
        return

    extract_result = run_api_step(
        scenario_output,
        lambda: run_single_vo_api(
            game_path=game_path,
            output_path=scenario_output,
            champion_id=champion_id,
            with_bp_vo=args.with_bp_vo,
            log_level=ctx.log_level,
            workers=ctx.workers,
            exclude_type=exclude_type,
        ),
    )
    add_result(
        results,
        runner=ctx.runner,
        scenario="single_vo",
        step="extract",
        output_root=scenario_output,
        command=f"api:extract(champion_id={champion_id}, include_maps=False)",
        data={**extract_result, "champion_id": champion_id},
    )


def run_targeted_scenario(  # noqa: PLR0913
    ctx: BenchmarkContext,
    args: argparse.Namespace,
    *,
    game_path: Path,
    scenario: str,
    scenario_output: Path,
    champion_ids: tuple[str, ...],
    map_ids: tuple[str, ...],
    update_map_ids: tuple[str, ...],
    results: list[dict[str, Any]],
) -> None:
    """执行显式英雄或地图目标的更新与解包场景。"""
    scenario_output.mkdir(parents=True, exist_ok=True)
    exclude_type = args.targeted_exclude_type
    targets = {"champion_ids": list(champion_ids), "map_ids": list(map_ids)}

    if args.prepare_update:
        if ctx.runner == "cli":
            update_cmd = build_update_command(
                ctx,
                game_path,
                scenario_output,
                skip_events=args.skip_events,
                with_bp_vo=args.with_bp_vo,
                champion_ids=champion_ids,
                map_ids=update_map_ids,
            )
            update_result = run_cli_step(
                ctx, cmd=update_cmd, output_root=scenario_output, step_name=f"{scenario}_update"
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario=scenario,
                step="update",
                output_root=scenario_output,
                command=" ".join(update_cmd),
                data={**update_result, "targets": targets},
            )
        else:
            update_result = run_api_step(
                scenario_output,
                lambda: run_update_api(
                    game_path=game_path,
                    output_path=scenario_output,
                    skip_events=args.skip_events,
                    with_bp_vo=args.with_bp_vo,
                    log_level=ctx.log_level,
                    workers=ctx.workers,
                    exclude_type=exclude_type,
                    champion_ids=champion_ids,
                    map_ids=update_map_ids,
                ),
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario=scenario,
                step="update",
                output_root=scenario_output,
                command=f"api:update(champion_ids={champion_ids}, map_ids={update_map_ids})",
                data={**update_result, "targets": targets},
            )
        if update_result.get("status") != "ok":
            return

    if ctx.runner == "cli":
        extract_cmd = build_targeted_extract_command(
            ctx,
            game_path,
            scenario_output,
            champion_ids=champion_ids,
            map_ids=map_ids,
            exclude_type=exclude_type,
            with_bp_vo=args.with_bp_vo,
        )
        extract_result = run_cli_step(
            ctx,
            cmd=extract_cmd,
            output_root=scenario_output,
            step_name=f"{scenario}_extract",
        )
        add_result(
            results,
            runner=ctx.runner,
            scenario=scenario,
            step="extract",
            output_root=scenario_output,
            command=" ".join(extract_cmd),
            data={**extract_result, "targets": targets},
        )
        return

    extract_result = run_api_step(
        scenario_output,
        lambda: run_targeted_extract_api(
            game_path=game_path,
            output_path=scenario_output,
            champion_ids=champion_ids,
            map_ids=map_ids,
            with_bp_vo=args.with_bp_vo,
            log_level=ctx.log_level,
            workers=ctx.workers,
            exclude_type=exclude_type,
        ),
    )
    add_result(
        results,
        runner=ctx.runner,
        scenario=scenario,
        step="extract",
        output_root=scenario_output,
        command=f"api:extract(champion_ids={champion_ids}, map_ids={map_ids})",
        data={**extract_result, "targets": targets},
    )


def run_full_extract_scenario(
    ctx: BenchmarkContext,
    args: argparse.Namespace,
    *,
    game_path: Path,
    scenario_output: Path,
    results: list[dict[str, Any]],
) -> None:
    """执行 full_extract 场景（更新 -> 全量解包）。"""
    scenario_output.mkdir(parents=True, exist_ok=True)
    exclude_type = args.full_extract_exclude_type

    if args.prepare_update:
        if ctx.runner == "cli":
            update_cmd = build_update_command(
                ctx,
                game_path,
                scenario_output,
                skip_events=args.skip_events,
                with_bp_vo=args.with_bp_vo,
            )
            update_result = run_cli_step(
                ctx,
                cmd=update_cmd,
                output_root=scenario_output,
                step_name="full_extract_update",
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="full_extract",
                step="update",
                output_root=scenario_output,
                command=" ".join(update_cmd),
                data=update_result,
            )
        else:
            update_result = run_api_step(
                scenario_output,
                lambda: run_update_api(
                    game_path=game_path,
                    output_path=scenario_output,
                    skip_events=args.skip_events,
                    with_bp_vo=args.with_bp_vo,
                    log_level=ctx.log_level,
                    workers=ctx.workers,
                    exclude_type=exclude_type,
                ),
            )
            add_result(
                results,
                runner=ctx.runner,
                scenario="full_extract",
                step="update",
                output_root=scenario_output,
                command="api:update(target=all)",
                data=update_result,
            )
        if update_result.get("status") != "ok":
            return

    if ctx.runner == "cli":
        extract_cmd = build_full_extract_command(
            ctx,
            game_path,
            scenario_output,
            exclude_type=exclude_type,
            with_bp_vo=args.with_bp_vo,
        )
        extract_result = run_cli_step(
            ctx,
            cmd=extract_cmd,
            output_root=scenario_output,
            step_name="full_extract_extract",
        )
        add_result(
            results,
            runner=ctx.runner,
            scenario="full_extract",
            step="extract",
            output_root=scenario_output,
            command=" ".join(extract_cmd),
            data=extract_result,
        )
        return

    extract_result = run_api_step(
        scenario_output,
        lambda: run_full_extract_api(
            game_path=game_path,
            output_path=scenario_output,
            with_bp_vo=args.with_bp_vo,
            log_level=ctx.log_level,
            workers=ctx.workers,
            exclude_type=exclude_type,
        ),
    )
    add_result(
        results,
        runner=ctx.runner,
        scenario="full_extract",
        step="extract",
        output_root=scenario_output,
        command="api:extract(all)",
        data=extract_result,
    )


def run_for_runner(  # noqa: PLR0913
    args: argparse.Namespace,
    *,
    runner: str,
    game_path: Path,
    output_path: Path,
    repo_root: Path,
    source: BenchmarkSource,
    results: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    target_champion_ids: tuple[str, ...],
    target_map_ids: tuple[str, ...],
) -> None:
    """按指定执行引擎运行目标场景。"""
    workers = resolve_workers(args.max_workers)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx = BenchmarkContext(
        repo_root=repo_root,
        runner=runner,
        uv_entry=args.uv_entry,
        timeout=args.timeout,
        workers=workers,
        log_level=args.log_level,
        run_id=run_id,
        source=source,
    )

    base_run_dir = output_path / "benchmark_runs" / f"{ctx.run_id}_{runner}"
    if args.mode in {"single_vo", "both"}:
        scenario_output = base_run_dir / "single_vo"
        first_row = len(results)
        run_single_vo_scenario(
            ctx,
            args,
            game_path=game_path,
            scenario_output=scenario_output,
            results=results,
        )
        summaries.append(
            build_scenario_summary(
                results[first_row:],
                runner=runner,
                scenario="single_vo",
                output_root=scenario_output,
                source=source,
            )
        )

    if args.mode == "targeted":
        try:
            game_version = get_game_version(game_path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            add_result(
                results,
                runner=runner,
                scenario="targeted",
                step="precheck",
                output_root=base_run_dir,
                command="",
                data={"status": "fail", "error": f"{type(e).__name__}: {e}"},
            )
            return
        if target_champion_ids:
            scenario_output = base_run_dir / "targeted_champion"
            first_row = len(results)
            run_targeted_scenario(
                ctx,
                args,
                game_path=game_path,
                scenario="targeted_champion",
                scenario_output=scenario_output,
                champion_ids=target_champion_ids,
                map_ids=(),
                update_map_ids=(),
                results=results,
            )
            summaries.append(
                build_targeted_summary(
                    results[first_row:],
                    runner=runner,
                    scenario="targeted_champion",
                    output_root=scenario_output,
                    source=source,
                    game_version=game_version,
                    champion_ids=target_champion_ids,
                )
            )

        if target_map_ids:
            scenario_output = base_run_dir / "targeted_map"
            update_map_ids = with_common_map(target_map_ids)
            first_row = len(results)
            run_targeted_scenario(
                ctx,
                args,
                game_path=game_path,
                scenario="targeted_map",
                scenario_output=scenario_output,
                champion_ids=(),
                map_ids=target_map_ids,
                update_map_ids=update_map_ids,
                results=results,
            )
            summaries.append(
                build_targeted_summary(
                    results[first_row:],
                    runner=runner,
                    scenario="targeted_map",
                    output_root=scenario_output,
                    source=source,
                    game_version=game_version,
                    map_ids=target_map_ids,
                    diagnostic_map_ids=update_map_ids,
                )
            )

    if args.mode in {"full_extract", "both"}:
        scenario_output = base_run_dir / "full_extract"
        first_row = len(results)
        run_full_extract_scenario(
            ctx,
            args,
            game_path=game_path,
            scenario_output=scenario_output,
            results=results,
        )
        summaries.append(
            build_scenario_summary(
                results[first_row:],
                runner=runner,
                scenario="full_extract",
                output_root=scenario_output,
                source=source,
            )
        )


def resolve_runtime_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    """解析运行路径。"""
    return args.game_path, args.output_path


def main() -> int:
    """脚本主入口。"""
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    source = BenchmarkSource(root=(args.source_root or repo_root).resolve(), label=args.source_label)
    source_runner_error = _source_runner_error(args.runner, source, repo_root)
    results: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    if not args.enable_league_tools_log:
        logger.disable("league_tools")

    try:
        target_champion_ids = parse_target_ids(args.target_champions, option_name="--target-champions")
        target_map_ids = parse_target_ids(args.target_maps, option_name="--target-maps")
        target_ids_valid = True
    except ValueError as e:
        target_champion_ids = ()
        target_map_ids = ()
        target_ids_valid = False
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="targeted_ids",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": str(e)},
        )

    game_path, output_path = resolve_runtime_paths(args)
    if target_ids_valid and (game_path is None or not game_path.exists()):
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="game_path",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": "未提供有效 GAME_PATH（请使用 --game-path）"},
        )
    elif target_ids_valid and not (source.root / "src").is_dir():
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="source_root",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": f"SOURCE_ROOT 缺少 src 目录: {source.root}"},
        )
    elif target_ids_valid and source_runner_error:
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="source_runner",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": source_runner_error},
        )
    elif target_ids_valid and output_path is None:
        add_result(
            results,
            runner="n/a",
            scenario="precheck",
            step="output_path",
            output_root=repo_root,
            command="",
            data={"status": "fail", "error": "未提供 OUTPUT_PATH（请使用 --output-path）"},
        )
    elif target_ids_valid and args.mode == "targeted" and not (target_champion_ids or target_map_ids):
        add_result(
            results,
            runner="n/a",
            scenario="targeted",
            step="precheck",
            output_root=output_path,
            command="",
            data={"status": "fail", "error": "targeted 模式需要 --target-champions 或 --target-maps"},
        )
    elif target_ids_valid:
        output_path.mkdir(parents=True, exist_ok=True)
        runners = [args.runner] if args.runner != "both" else ["cli", "api"]
        for runner in runners:
            run_for_runner(
                args,
                runner=runner,
                game_path=game_path,
                output_path=output_path,
                repo_root=repo_root,
                source=source,
                results=results,
                summaries=summaries,
                target_champion_ids=target_champion_ids,
                target_map_ids=target_map_ids,
            )

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "mode": args.mode,
            "runner": args.runner,
            "prepare_update": args.prepare_update,
            "skip_events": args.skip_events,
            "target_champion_ids": list(target_champion_ids),
            "target_map_ids": list(target_map_ids),
            "workers": resolve_workers(args.max_workers),
            "platform": platform.platform(),
            "source_label": source.label,
            "source_root": str(source.root),
            "game_path": str(game_path) if game_path else "",
            "output_path": str(output_path) if output_path else "",
        },
        "results": results,
        "summaries": summaries,
    }

    output_json = args.output if args.output.is_absolute() else repo_root / args.output
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [row for row in results if row.get("status") in {"fail", "timeout"}]
    print(f"基准完成，结果已写入: {output_json}")
    print(f"总步骤: {len(results)}，失败步骤: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
