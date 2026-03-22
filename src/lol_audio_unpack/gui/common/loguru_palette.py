"""loguru 默认 ANSI 颜色检测结果与 GUI 固定色表。"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AnsiStyleSpec:
    """描述一段 ANSI 文本的前景、背景与粗体属性。"""

    fg_sgr: int | None = None
    bg_sgr: int | None = None
    bold: bool = False

    def to_dict(self) -> dict[str, int | bool | None]:
        """将当前样式转换为便于序列化的字典。"""
        return asdict(self)


LOGURU_DEFAULT_ANSI_DETECTION_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>|"
    "<level>{level: <8}</level>|"
    "<cyan>LOCATION</cyan>|"
    "<level>{message}</level>"
)

LOGURU_DEFAULT_SEGMENT_ANSI_STYLES: dict[str, AnsiStyleSpec] = {
    "time": AnsiStyleSpec(fg_sgr=32),
    "location": AnsiStyleSpec(fg_sgr=36),
}

LOGURU_DEFAULT_LEVEL_ANSI_STYLES: dict[str, AnsiStyleSpec] = {
    "TRACE": AnsiStyleSpec(fg_sgr=36, bold=True),
    "DEBUG": AnsiStyleSpec(fg_sgr=34, bold=True),
    "INFO": AnsiStyleSpec(bold=True),
    "SUCCESS": AnsiStyleSpec(fg_sgr=32, bold=True),
    "WARNING": AnsiStyleSpec(fg_sgr=33, bold=True),
    "ERROR": AnsiStyleSpec(fg_sgr=31, bold=True),
    "CRITICAL": AnsiStyleSpec(bg_sgr=41, bold=True),
}

# 固定到项目内的 ANSI -> GUI 颜色映射。
# 这里选用 Windows Terminal / PowerShell 常见的 Campbell 配色，保证与用户当前环境更接近，
# 同时又不依赖外部终端运行时才能稳定复现。
ANSI_FIXED_HEX_BY_SGR: dict[int, str] = {
    31: "#C50F1F",
    32: "#13A10E",
    33: "#C19C00",
    34: "#0037DA",
    36: "#3A96DD",
    41: "#C50F1F",
}


def build_detected_style_payload() -> dict[str, dict[str, dict[str, int | bool | None]]]:
    """返回可供脚本输出或测试断言的固定 ANSI 样式描述。"""
    return {
        "segments": {name: style.to_dict() for name, style in LOGURU_DEFAULT_SEGMENT_ANSI_STYLES.items()},
        "levels": {name: style.to_dict() for name, style in LOGURU_DEFAULT_LEVEL_ANSI_STYLES.items()},
    }
