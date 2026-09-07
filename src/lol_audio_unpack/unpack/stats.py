"""音频解包统计与报告工具。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lol_audio_unpack.app.results import FailureDetail

from ..manager.utils import build_metadata_payload
from ..utils.common import dump_yaml, format_duration


class StageResult(Enum):
    """处理阶段结果枚举"""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


class FileProcessResult(Enum):
    """文件处理结果枚举"""

    SUCCESS = "success"
    EMPTY_CONTAINER = "empty_container"
    EMPTY_SUBFILE = "empty_subfile"
    PARSE_ERROR = "parse_error"
    UNKNOWN_TYPE = "unknown_type"


@dataclass
class WadExtractionInfo:
    """WAD文件解包信息

    :param wad_path: WAD文件路径
    :param requested_files: 请求解包的文件数量
    :param extracted_files: 实际解包成功的文件数量
    :param failed: 是否解包失败
    :param error_message: 错误信息（如果有）
    """

    wad_path: Path | None = None
    requested_files: int = 0
    extracted_files: int = 0
    failed: bool = False
    error_message: str | None = None


@dataclass
class SubEntityStats:
    """子实体（皮肤/地图变体）统计信息

    :param sub_id: 子实体ID
    :param name: 子实体名称
    :param total_files: 总文件数
    :param success_files: 成功处理的文件数
    :param empty_containers: 空容器文件数
    :param empty_subfiles: 空子文件数
    :param failed_files: 处理失败的文件数
    :param unknown_types: 未知类型文件数
    :param stats_by_type: 按音频类型分组的统计信息
    :param failed_file_details: 失败文件的详细信息
    :param empty_container_paths: 空容器文件的路径列表
    """

    sub_id: int | str
    name: str
    total_files: int = 0
    success_files: int = 0
    empty_containers: int = 0
    empty_subfiles: int = 0
    failed_files: int = 0
    unknown_types: int = 0

    # 按音频类型分组的统计
    stats_by_type: dict[str, dict[str, int]] = field(default_factory=dict)

    # 详细的错误信息
    failed_file_details: list[dict[str, Any]] = field(default_factory=list)
    empty_container_paths: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """是否存在问题（失败或跳过的文件）"""
        return self.failed_files > 0 or self.unknown_types > 0 or self.empty_containers > 0


@dataclass
class EntityUnpackStats:
    """实体解包统计信息收集器

    这个类负责收集整个实体（英雄/地图）解包过程中的所有统计信息，
    包括各个处理阶段的结果、文件处理详情、错误信息等。
    """

    # === 基本信息 ===
    entity_id: int | str
    entity_name: str
    entity_type: str  # 英雄、地图或资源包
    game_version: str  # 游戏版本号
    language: str
    languages: list[str] = field(default_factory=list)  # 语言列表（用于元数据生成）
    included_types: list[str] = field(default_factory=list)
    excluded_types: set[str] = field(default_factory=set)

    # === 阶段1: 路径收集统计 ===
    total_sub_entities: int = 0
    processed_sub_entities: int = 0
    skipped_sub_entities: int = 0
    skipped_sub_entity_details: list[str] = field(default_factory=list)

    vo_paths_count: int = 0
    sfx_music_paths_count: int = 0

    # === 阶段2: WAD解包统计 ===
    vo_wad_info: WadExtractionInfo = field(default_factory=WadExtractionInfo)
    root_wad_info: WadExtractionInfo = field(default_factory=WadExtractionInfo)
    binding_completeness: str | None = None
    binding_details: list[dict[str, Any]] = field(default_factory=list)
    binding_wads: list[dict[str, Any]] = field(default_factory=list)
    file_failures: list[FailureDetail] = field(default_factory=list)

    # === 阶段3: 数据组装统计 ===
    assembled_sub_entities: int = 0
    total_assembled_files: int = 0

    # === 阶段4: 文件处理统计 ===
    sub_entity_stats: dict[int | str, SubEntityStats] = field(default_factory=dict)

    # === 整体汇总 ===
    total_success_files: int = 0
    total_failed_files: int = 0
    total_skipped_files: int = 0

    overall_result: StageResult = StageResult.SUCCESS
    start_time: float | None = None
    end_time: float | None = None

    def start_processing(self) -> None:
        """开始处理，记录开始时间"""

        self.start_time = time.time()

    def finish_processing(self) -> None:
        """结束处理，记录结束时间并计算整体结果"""

        self.end_time = time.time()
        self._calculate_overall_result()

    def get_processing_duration(self) -> float:
        """获取处理耗时（毫秒）

        :returns: 处理耗时，单位毫秒
        """
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def record_sub_entity_skipped(self, sub_id: str, reason: str) -> None:
        """记录跳过的子实体

        :param sub_id: 子实体ID
        :param reason: 跳过原因
        """
        self.skipped_sub_entities += 1
        self.skipped_sub_entity_details.append(f"子实体ID {sub_id}: {reason}")

    def set_wad_info(
        self, wad_type: str, wad_path: Path | None, requested: int, extracted: int, error: str | None = None
    ) -> None:
        """设置WAD解包信息

        :param wad_type: WAD类型，"VO" 或 "ROOT"
        :param wad_path: WAD文件路径
        :param requested: 请求解包的文件数量
        :param extracted: 实际解包成功的文件数量
        :param error: 错误信息（如果有）
        """
        wad_info = WadExtractionInfo(
            wad_path=wad_path,
            requested_files=requested,
            extracted_files=extracted,
            failed=bool(error),
            error_message=error,
        )

        if wad_type == "VO":
            self.vo_wad_info = wad_info
        else:
            self.root_wad_info = wad_info

    def get_or_create_sub_stats(self, sub_id: int | str, name: str) -> SubEntityStats:
        """获取或创建子实体统计对象

        :param sub_id: 子实体ID
        :param name: 子实体名称
        :returns: 子实体统计对象
        """
        if sub_id not in self.sub_entity_stats:
            self.sub_entity_stats[sub_id] = SubEntityStats(sub_id=sub_id, name=name)
        return self.sub_entity_stats[sub_id]

    def record_file_result(
        self, sub_id: int | str, sub_name: str, audio_type: str, result: FileProcessResult, **details
    ) -> None:
        """记录文件处理结果

        :param sub_id: 子实体ID
        :param sub_name: 子实体名称
        :param audio_type: 音频类型
        :param result: 处理结果
        :param details: 额外的详细信息
        """
        sub_stats = self.get_or_create_sub_stats(sub_id, sub_name)
        sub_stats.total_files += 1

        # 确保音频类型统计存在
        if audio_type not in sub_stats.stats_by_type:
            sub_stats.stats_by_type[audio_type] = {
                "total": 0,
                "success": 0,
                "empty_container": 0,
                "empty_subfile": 0,
                "failed": 0,
                "unknown": 0,
            }

        type_stats = sub_stats.stats_by_type[audio_type]
        type_stats["total"] += 1

        if result == FileProcessResult.SUCCESS:
            sub_stats.success_files += 1
            type_stats["success"] += 1
        elif result == FileProcessResult.EMPTY_CONTAINER:
            sub_stats.empty_containers += 1
            type_stats["empty_container"] += 1
            if source_path := details.get("source_path"):
                sub_stats.empty_container_paths.append(source_path)
        elif result == FileProcessResult.EMPTY_SUBFILE:
            sub_stats.empty_subfiles += 1
            type_stats["empty_subfile"] += 1
        elif result == FileProcessResult.UNKNOWN_TYPE:
            sub_stats.unknown_types += 1
            type_stats["unknown"] += 1
            if error_info := details.get("error_info"):
                sub_stats.failed_file_details.append(error_info)
        else:  # PARSE_ERROR
            sub_stats.failed_files += 1
            type_stats["failed"] += 1
            if error_info := details.get("error_info"):
                sub_stats.failed_file_details.append(error_info)

    def record_assembly_stats(self, assembled_entities: int, total_files: int) -> None:
        """记录数据组装阶段的统计信息

        :param assembled_entities: 组装的子实体数量
        :param total_files: 组装的总文件数
        """
        self.assembled_sub_entities = assembled_entities
        self.total_assembled_files = total_files

    def record_binding_result(  # noqa: PLR0913
        self,
        *,
        sub_id: str,
        audio_type: str,
        category: str,
        path: str,
        wad: str | None,
        entry_hash: str,
        status: str,
        outcome: str,
        error: str | None = None,
    ) -> None:
        """记录逐条 binding 的消费结果，不持久化本机绝对 WAD 路径。"""
        detail: dict[str, Any] = {
            "subEntity": sub_id,
            "audioType": audio_type,
            "category": category,
            "path": path,
            "wad": wad,
            "entryHash": entry_hash,
            "status": status,
            "outcome": outcome,
        }
        if error:
            detail["error"] = error
        self.binding_details.append(detail)

    def record_binding_wad(
        self,
        wad: str,
        *,
        requested: int,
        extracted: int,
        error: str | None = None,
    ) -> None:
        """记录一个物理 WAD 的 binding 提取诊断。"""
        detail: dict[str, Any] = {
            "wad": wad,
            "requested": requested,
            "extracted": extracted,
            "success": error is None,
        }
        if error:
            detail["error"] = error
        self.binding_wads.append(detail)

    def set_binding_completeness(self, source_completeness: str) -> None:
        """从 binding 结果与 P1 解析诊断派生实体完整度。"""
        processable = [
            detail for detail in self.binding_details if detail["status"] in {"resolved", "ambiguous_identical"}
        ]
        successful = [detail for detail in processable if detail["outcome"] in {"success", "partial"}]
        has_failure = any(
            detail["outcome"] in {"failed", "unresolved", "partial", "write_failed"} for detail in self.binding_details
        )

        # 全部是合法无内嵌音频的 BNK 时允许成功 no-op；这些空结果不能把真实失败抬成部分成功。
        if processable and all(detail["outcome"] == "no_audio" for detail in processable):
            if source_completeness == "complete" and not has_failure:
                self.binding_completeness = "complete"
                return
        if not processable or not successful:
            self.binding_completeness = "failed"
            return
        if source_completeness != "complete" or has_failure:
            self.binding_completeness = "partial"
            return
        self.binding_completeness = "complete"

    def _calculate_overall_result(self) -> None:
        """计算整体处理结果"""
        # 计算总计数
        for sub_stats in self.sub_entity_stats.values():
            self.total_success_files += sub_stats.success_files
            self.total_failed_files += sub_stats.failed_files + sub_stats.unknown_types
            self.total_skipped_files += sub_stats.empty_containers + sub_stats.empty_subfiles

        # binding 驱动阶段需要用实体级 complete/partial/failed 覆盖旧双 WAD 结论；
        # 未提供 binding 诊断的兼容调用方仍保持原有统计语义。
        if self.binding_completeness == "failed":
            self.overall_result = StageResult.ERROR
        elif self.binding_completeness == "partial":
            self.overall_result = StageResult.WARNING
        elif self.binding_completeness == "complete":
            self.overall_result = StageResult.SUCCESS
        elif self.vo_wad_info.failed or self.root_wad_info.failed:
            self.overall_result = StageResult.ERROR
        elif self.total_failed_files > 0:
            if self.total_success_files > 0 or self.total_skipped_files > 0 or self.skipped_sub_entities > 0:
                self.overall_result = StageResult.WARNING
            else:
                self.overall_result = StageResult.ERROR
        elif self.total_skipped_files > 0 or self.skipped_sub_entities > 0:
            self.overall_result = StageResult.WARNING
        else:
            self.overall_result = StageResult.SUCCESS

    def get_simple_summary(self) -> str:
        """生成简洁的汇总信息

        :returns: 简洁的汇总字符串
        """

        duration_str = format_duration(self.get_processing_duration())
        binding_errors = {
            (detail["wad"], detail["entryHash"], detail["path"]): detail
            for detail in self.binding_details
            if detail["outcome"] in {"failed", "unresolved"}
        }
        issue_text = ""
        if binding_errors:
            first = next(iter(binding_errors.values()))
            issue_text = (
                f"；{len(binding_errors)} 个资源容器未完成，"
                f"首项 {Path(first['path']).name}：{first.get('error') or first['outcome']}"
            )
        elif self.binding_completeness == "partial":
            issue_text = "；基础资源清单不完整，请重新生成实体数据"

        if self.overall_result == StageResult.SUCCESS:
            return f"✅ {self.entity_name} 解包完成 - 成功 {self.total_success_files} 个文件 ({duration_str})"
        elif self.overall_result == StageResult.WARNING:
            details = []
            if self.total_failed_files > 0:
                details.append(f"失败 {self.total_failed_files}")
            if self.total_skipped_files > 0:
                details.append(f"跳过 {self.total_skipped_files}")
            if self.skipped_sub_entities > 0:
                details.append(f"跳过子实体 {self.skipped_sub_entities}")
            detail_str = f" ({', '.join(details)})" if details else ""
            return f"⚠️ {self.entity_name} 解包完成 - 成功 {self.total_success_files} 个文件{detail_str}{issue_text} ({duration_str})"
        else:
            return (
                f"❌ {self.entity_name} 解包失败 - 成功 {self.total_success_files}, "
                f"失败 {self.total_failed_files}{issue_text} ({duration_str})"
            )

    def generate_concise_report_data(self) -> dict[str, Any]:
        """生成简洁的YAML报告数据

        :returns: 简洁清晰的报告字典
        """
        metadata = build_metadata_payload(self.game_version, self.languages)

        duration_ms = self.get_processing_duration()

        # 简洁的报告结构
        report = {
            "entity": {
                "id": self.entity_id,
                "name": self.entity_name,
                "type": self.entity_type,
            },
            "processing": {
                "duration_ms": duration_ms,
                "language": self.language,
                "audio_types": self.included_types,
                "result": self.overall_result.value,
            },
            "wad_files": {},
            "summary": {
                "total_success": self.total_success_files,
                "total_failed": self.total_failed_files,
                "total_skipped": self.total_skipped_files,
            },
            "sub_entities": {},
        }

        if self.binding_completeness is not None:
            report["bindingDiagnostics"] = {
                "completeness": self.binding_completeness,
                "bindings": self.binding_details,
                "wads": self.binding_wads,
            }

        # WAD文件信息
        if self.vo_wad_info.wad_path:
            report["wad_files"]["vo"] = {
                "file": self.vo_wad_info.wad_path.name,
                "extracted": f"{self.vo_wad_info.extracted_files}/{self.vo_wad_info.requested_files}",
                "success": not self.vo_wad_info.failed,
            }

        if self.root_wad_info.wad_path:
            report["wad_files"]["sfx_music"] = {
                "file": self.root_wad_info.wad_path.name,
                "extracted": f"{self.root_wad_info.extracted_files}/{self.root_wad_info.requested_files}",
                "success": not self.root_wad_info.failed,
            }

        # 各子实体的统计
        for sub_stats in self.sub_entity_stats.values():
            sub_entity_data = {
                "id": sub_stats.sub_id,
                "total": sub_stats.total_files,
                "success": sub_stats.success_files,
                "failed": sub_stats.failed_files,
                "skipped": sub_stats.empty_containers + sub_stats.empty_subfiles,
                "audio_types": {},
            }

            # 如果有跳过的文件，记录详细信息
            if sub_stats.empty_containers > 0 or sub_stats.empty_subfiles > 0:
                sub_entity_data["skipped_details"] = {
                    "empty_containers": sub_stats.empty_containers,
                    "empty_subfiles": sub_stats.empty_subfiles,
                }

                # 记录空容器的路径
                if sub_stats.empty_container_paths:
                    sub_entity_data["skipped_details"]["empty_container_paths"] = sub_stats.empty_container_paths

            # 各音频类型的统计
            for audio_type, type_stats in sub_stats.stats_by_type.items():
                if type_stats["total"] > 0:
                    audio_type_data = {
                        "success": type_stats["success"],
                        "total": type_stats["total"],
                    }

                    # 如果有跳过的文件，添加详细信息
                    skipped_count = type_stats["empty_container"] + type_stats["empty_subfile"]
                    if skipped_count > 0:
                        audio_type_data["skipped"] = skipped_count
                        audio_type_data["skipped_breakdown"] = {
                            "empty_containers": type_stats["empty_container"],
                            "empty_subfiles": type_stats["empty_subfile"],
                        }

                    sub_entity_data["audio_types"][audio_type] = audio_type_data

            report["sub_entities"][sub_stats.name] = sub_entity_data

        if self.file_failures:
            report["fileFailures"] = [asdict(item) for item in self.file_failures]
        metadata["report"] = report
        return metadata

    def save_concise_report_to_yaml(self, file_path: Path) -> None:
        """保存简洁报告到YAML文件

        :param file_path: 保存路径
        """
        report_data = self.generate_concise_report_data()
        dump_yaml(report_data, file_path)


class ProcessingStatsContext:
    """处理统计上下文管理器

    使用上下文管理器模式，自动处理统计的开始和结束。
    不包含任何日志逻辑，只负责数据收集。

    :param entity_data: 实体数据
    :param game_version: 游戏版本号
    :param language: 语言
    :param included_types: 包含的音频类型
    :param excluded_types: 排除的音频类型
    """

    def __init__(
        self, entity_data, game_version: str, language: str, included_types: list[str], excluded_types: set[str]
    ):
        self.stats = EntityUnpackStats(
            entity_id=entity_data.entity_id,
            entity_name=entity_data.entity_name,
            entity_type=entity_data.entity_type,
            game_version=game_version,
            language=language,
            languages=[language],  # 目前只支持单语言，转换为列表格式
            included_types=included_types,
            excluded_types=excluded_types,
        )

    def __enter__(self) -> EntityUnpackStats:
        """进入上下文，开始统计"""
        self.stats.start_processing()
        return self.stats

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文，结束统计"""
        self.stats.finish_processing()
