"""共享的同目录原子文件发布与失败阶段。"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from loguru import logger


class ArtifactWriteError(OSError):
    """结构化 artifact 未能完整替换目标文件。

    原始异常通过异常链保留，调用方无需从日志文本推断失败原因。

    Args:
        path: 原本要替换的正式目标路径。
        stage: 失败阶段，例如 ``serialize``、``fsync`` 或 ``replace``。
    """

    def __init__(self, path: Path, stage: str) -> None:
        self.path = Path(path)
        self.stage = stage
        super().__init__(f"artifact 写入失败（{stage}）: {self.path}")


def replace_file(target: Path, writer: Callable[[Path], object], *, write_stage: str) -> Path:
    """在目标同目录准备完整文件后执行原子替换。

    Args:
        target: 带后缀的正式目标路径。
        writer: 只向所给临时路径写入完整内容的函数。
        write_stage: writer 失败时写入语义异常的阶段名。

    Returns:
        成功替换的目标路径。

    Raises:
        ArtifactWriteError: 准备、写入、同步或替换失败。
    """
    temp_path: Path | None = None
    stage = "prepare"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        os.close(descriptor)

        stage = write_stage
        writer(temp_path)

        # Windows 的 fsync 需要可写句柄；内容不再修改，只借此确保 replace 前完成文件同步。
        stage = "fsync"
        with temp_path.open("r+b") as file:
            os.fsync(file.fileno())

        stage = "replace"
        os.replace(temp_path, target)
        return target
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.opt(exception=True).warning(f"清理 artifact 临时文件失败: {temp_path}")
        raise ArtifactWriteError(target, stage) from exc
