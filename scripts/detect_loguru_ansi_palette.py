"""检测 loguru 默认 ANSI 颜色，并校验项目内固定色表。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from loguru import logger  # noqa: E402

from lol_audio_unpack.gui.common.loguru_palette import (  # noqa: E402
    LOGURU_DEFAULT_ANSI_DETECTION_FORMAT,
    LOGURU_DEFAULT_LEVEL_ANSI_STYLES,
    build_detected_style_payload,
)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[([0-9;]+)m")
ANSI_BOLD_CODE = 1
ANSI_FG_STANDARD_MIN = 30
ANSI_FG_STANDARD_MAX = 37
ANSI_FG_BRIGHT_MIN = 90
ANSI_FG_BRIGHT_MAX = 97
ANSI_BG_STANDARD_MIN = 40
ANSI_BG_STANDARD_MAX = 47
ANSI_BG_BRIGHT_MIN = 100
ANSI_BG_BRIGHT_MAX = 107


def _parse_ansi_style(segment_text: str) -> dict[str, int | bool | None]:
    """从 ANSI 片段中解析前景、背景与粗体状态。"""
    style = {"fg_sgr": None, "bg_sgr": None, "bold": False}
    for match in ANSI_ESCAPE_RE.finditer(segment_text):
        for code_text in match.group(1).split(";"):
            if not code_text:
                continue
            code = int(code_text)
            if code == ANSI_BOLD_CODE:
                style["bold"] = True
            elif ANSI_FG_STANDARD_MIN <= code <= ANSI_FG_STANDARD_MAX or ANSI_FG_BRIGHT_MIN <= code <= ANSI_FG_BRIGHT_MAX:
                style["fg_sgr"] = code
            elif ANSI_BG_STANDARD_MIN <= code <= ANSI_BG_STANDARD_MAX or ANSI_BG_BRIGHT_MIN <= code <= ANSI_BG_BRIGHT_MAX:
                style["bg_sgr"] = code
    return style


def _capture_loguru_styles() -> dict[str, dict[str, dict[str, int | bool | None]]]:
    """捕获 loguru 在当前环境下的默认 ANSI 样式。"""
    captured: list[str] = []
    detection_levels = tuple(LOGURU_DEFAULT_LEVEL_ANSI_STYLES)

    logger.remove()
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        colorize=True,
        level="TRACE",
        format=LOGURU_DEFAULT_ANSI_DETECTION_FORMAT,
    )
    try:
        for level in detection_levels:
            logger.log(level, level)
    finally:
        logger.remove(sink_id)

    payload = {"segments": {}, "levels": {}}
    for level, line in zip(detection_levels, captured, strict=True):
        time_text, level_text, location_text, message_text = line.rstrip().split("|")
        payload["segments"]["time"] = _parse_ansi_style(time_text)
        payload["segments"]["location"] = _parse_ansi_style(location_text)
        payload["levels"][level] = _parse_ansi_style(level_text)
        payload["levels"][f"{level}:message"] = _parse_ansi_style(message_text)

    return payload


def main() -> int:
    """执行 ANSI 检测，并与项目内固定样式进行对比。"""
    detected = _capture_loguru_styles()
    expected = build_detected_style_payload()

    level_mismatches: dict[str, dict[str, dict[str, int | bool | None]]] = {}
    for level, expected_style in expected["levels"].items():
        detected_level_style = detected["levels"].get(level)
        detected_message_style = detected["levels"].get(f"{level}:message")
        if detected_level_style != expected_style or detected_message_style != expected_style:
            level_mismatches[level] = {
                "expected": expected_style,
                "detected_level": detected_level_style or {},
                "detected_message": detected_message_style or {},
            }

    segment_mismatches: dict[str, dict[str, dict[str, int | bool | None]]] = {}
    for segment, expected_style in expected["segments"].items():
        detected_style = detected["segments"].get(segment)
        if detected_style != expected_style:
            segment_mismatches[segment] = {
                "expected": expected_style,
                "detected": detected_style or {},
            }

    result = {
        "expected": expected,
        "detected": detected,
        "segment_mismatches": segment_mismatches,
        "level_mismatches": level_mismatches,
        "matched": not segment_mismatches and not level_mismatches,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
