"""独立 WEM 文件清单的解析与批量转码，不依赖游戏上下文。"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from ...app.audio_scope import AudioScope
from ...app.types import WavOutputOptions
from .batch import WavBatchResult, run_batch


def read_inputs(paths: list[Path], list_path: Path | None = None) -> tuple[Path, ...]:
    """读取显式文件与 UTF-8 清单，校验后按物理路径去重。

    Args:
        paths: 命令行文件路径，相对路径基于当前目录。
        list_path: 每行一个路径的文本文件；相对条目基于清单所在目录。

    Returns:
        完整且非空的 WEM 文件集合；空行忽略，不展开通配符。

    Raises:
        ValueError: 清单为空、文件不存在或扩展名不是 WEM。
    """
    inputs = list(paths)
    if list_path is not None:
        list_path = list_path.expanduser().resolve()
        for line in list_path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if not value:
                continue
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            path = Path(value).expanduser()
            inputs.append(path if path.is_absolute() else list_path.parent / path)
    sources = tuple(dict.fromkeys(path.expanduser().resolve() for path in inputs))
    if not sources:
        raise ValueError("请用 --input 或 --input-list 提供至少一个 WEM 文件")
    for path in sources:
        if path.suffix.lower() != ".wem" or not path.is_file():
            raise ValueError(f"WEM 输入不存在或不是 .wem 文件：{path}")
    return sources


def build_scopes(sources: tuple[Path, ...], input_root: Path | None = None) -> tuple[AudioScope, ...]:
    """按共同父目录构造镜像范围，同名 WEM 保留各自子目录。

    Args:
        sources: 已校验的绝对输入路径。
        input_root: 显式镜像根目录；省略时按各卷的共同父目录计算。

    Returns:
        按卷排序的范围；跨卷不能共用文件系统根，因此分批提交。

    Raises:
        ValueError: 显式输入根未覆盖所有文件。
    """
    if input_root is not None:
        root = input_root.expanduser().resolve()
        if any(not path.is_relative_to(root) for path in sources):
            raise ValueError("所有 WEM 输入必须位于 --input-root 目录内")
        return (AudioScope(root, files=tuple(path.relative_to(root).as_posix() for path in sources)),)
    volumes: dict[str, list[Path]] = {}
    for path in sources:
        volumes.setdefault(path.anchor, []).append(path)
    scopes = []
    for anchor in sorted(volumes):
        paths = volumes[anchor]
        root = Path(os.path.commonpath([path.parent for path in paths]))
        scopes.append(AudioScope(root, files=tuple(path.relative_to(root).as_posix() for path in paths)))
    return tuple(scopes)


def convert_files(
    scopes: tuple[AudioScope, ...],
    output_root: Path,
    *,
    options: WavOutputOptions,
    overwrite: bool = False,
) -> tuple[WavBatchResult, ...]:
    """复用主流程批处理，将指定 WEM 转为 WAV，报告写入输出下的 reports。

    Args:
        scopes: 已解析的精确文件范围，不扫描额外 WEM。
        output_root: WAV 目标目录。
        options: 与实体转码共用的并发、格式、重试和后端参数。
        overwrite: 是否覆盖已经存在的 WAV。

    Returns:
        每个卷的可靠批处理结果；不创建持久内容缓存。
    """
    results = []
    for index, scope in enumerate(scopes, start=1):
        destination = output_root if len(scopes) == 1 else output_root / f"volume-{index}"
        logger.info("独立 WEM 转码：{} 个文件，输入根 {}，输出 {}", len(scope.files), scope.root, destination)
        result = run_batch(
            scope,
            destination,
            options=options,
            report_root=output_root / "reports",
            overwrite=overwrite,
        )
        results.append(result)
        logger.info("转码报告：{}", result.report_path)
    return tuple(results)
