"""单实体导出的冻结请求，供 GUI 和后台执行器共享。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audio_scope import AudioScope
from .types import WavOutputOptions


@dataclass(frozen=True, slots=True)
class ExportTarget:
    """描述一个领域源目录与其对应的镜像输出位置。"""

    scope: AudioScope
    output_root: Path


@dataclass(frozen=True, slots=True)
class AudioExportRequest:
    """冻结单个实体的导出范围和一次性冲突策略。

    多个 target 仅兼容既有按音频类型分目录的输出布局，不表示跨实体选择。
    """

    entity_type: str
    entity_id: str
    entity_name: str
    version: str
    version_root: Path
    targets: tuple[ExportTarget, ...]
    report_root: Path
    options: WavOutputOptions
    overwrite: bool = False
    output_file: Path | None = None
    reveal_output: bool = False

    def validate(self) -> None:
        """在后台开始前复核冻结的版本路径与所有源目录边界。"""
        if not self.targets:
            raise ValueError("尚未选择导出音频")
        root = self.version_root.resolve()
        if root.name != self.version:
            raise ValueError("导出版本与音频目录不匹配，请重新选择当前实体")
        for target in self.targets:
            target.scope.root.resolve().relative_to(root)
        if self.output_file is not None and len(self.targets) != 1:
            raise ValueError("单文件另存为只能使用一个源目录")
