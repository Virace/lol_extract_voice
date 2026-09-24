"""与主动作编排分离的映射 JSON 导出和指定 WEM 转码命令。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from ..app.mapping_export import load_mapping, mapping_json
from ..app.types import WavOutputOptions
from ..runtime.wav.files import build_scopes, convert_files, read_inputs
from ..utils.atomic import replace_file
from .invocation import DEFAULT_GAME_REGION
from .text import text

FILE_COMMANDS = ("export-json", "convert-wem")


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须大于 0")
    return number


def _entity_id(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("实体 ID 不能为负数")
    return number


def create_file_parser(command: str) -> argparse.ArgumentParser:
    """创建独立命令解析器，拒绝组合主流程动作或读取主流程 INI。"""
    parser = argparse.ArgumentParser(prog=f"{Path(sys.argv[0]).name} {command}")
    if command == "export-json":
        parser.description = "按英雄或地图 ID 导出完整映射 JSON；请先执行 update mapping。"
        targets = parser.add_mutually_exclusive_group(required=True)
        targets.add_argument("--champions", type=_entity_id, metavar="ID", help="单个英雄 ID")
        targets.add_argument("--maps", type=_entity_id, metavar="ID", help="单个地图 ID，0 表示常规公共资源")
        parser.add_argument("--output-path", type=Path, default=Path("output"), help="主流程输出目录，默认 ./output")
        parser.add_argument("--game-version", help="已有映射版本；仅有一个匹配版本时可省略")
        parser.add_argument("--game-region", default=DEFAULT_GAME_REGION, help="映射语言，默认 %(default)s")
        parser.add_argument("--json-output", type=Path, help="另存为 .json 文件；省略时输出纯 JSON 到标准输出")
    else:
        parser.description = "独立 WEM 转 WAV，不需要游戏目录；同名文件保留相对目录。"
        defaults = WavOutputOptions()
        parser.add_argument("--input", type=Path, nargs="+", default=[], metavar="WEM", help="一个或多个 WEM 路径")
        parser.add_argument("--input-list", type=Path, help="UTF-8 文本清单，每行一个 WEM 路径")
        parser.add_argument("--input-root", type=Path, help="固定镜像根；默认使用输入文件的共同父目录")
        parser.add_argument(
            "--output-path", type=Path, default=Path("output/wavs"), help="WAV 目标目录，默认 ./output/wavs"
        )
        parser.add_argument(
            "--wav-workers", type=_positive, default=defaults.worker_count, help=text("help.wav_workers")
        )
        parser.add_argument(
            "--wav-timeout", type=_positive, default=defaults.timeout_seconds, help=text("help.wav_timeout")
        )
        parser.add_argument(
            "--wav-retries", type=_positive, default=defaults.max_retries, help=text("help.wav_retries")
        )
        parser.add_argument(
            "--wav-format",
            choices=("auto", "pcm16", "pcm24", "pcm32", "float"),
            default=defaults.format,
            help=text("help.wav_format"),
        )
        parser.add_argument("--vgmstream-path", type=Path, help="可选外部 vgmstream-cli；默认使用内置后端")
        parser.add_argument("--overwrite", action="store_true", help="覆盖已有 WAV；默认跳过")
    return parser


def _export_json(args: argparse.Namespace) -> int:
    entity_dir = "champions" if args.champions is not None else "maps"
    entity_id = args.champions if args.champions is not None else args.maps
    source, data = load_mapping(
        args.output_path.expanduser(),
        entity_dir=entity_dir,
        entity_id=entity_id,
        version=args.game_version,
        region=args.game_region,
    )
    payload = mapping_json(data)
    if args.json_output is None:
        sys.stdout.write(payload)
    else:
        target = args.json_output.expanduser().resolve()
        if target.suffix.lower() != ".json" or target == source.resolve():
            raise ValueError("--json-output 必须是独立的 .json 文件，不能覆盖映射来源")
        replace_file(target, lambda path: path.write_text(payload, encoding="utf-8"), write_stage="mapping-json")
        print(f"已导出 JSON：{target}", file=sys.stderr)
    return 0


def _convert_wem(args: argparse.Namespace) -> int:
    sources = read_inputs(args.input, args.input_list)
    scopes = build_scopes(sources, args.input_root)
    options = WavOutputOptions(
        enabled=True,
        worker_count=args.wav_workers,
        timeout_seconds=args.wav_timeout,
        max_retries=args.wav_retries,
        format=args.wav_format,
        backend_path=str(args.vgmstream_path.expanduser().resolve()) if args.vgmstream_path else None,
    )
    results = convert_files(scopes, args.output_path.expanduser().resolve(), options=options, overwrite=args.overwrite)
    if all(result.status == "success" for result in results):
        return 0
    return 3 if any(result.success_count or result.skipped_count for result in results) else 1


def run_file_command(argv: list[str]) -> int:
    """执行独立入口，将诊断留在 stderr，并沿用 CLI 的退出码约定。"""
    parser = create_file_parser(argv[0])
    args = parser.parse_args(argv[1:])
    # 不进入 setup_app，避免纯读映射或转码触发客户端预检、目录迁移与 stdout 日志。
    logger.remove()
    logger.enable("lol_audio_unpack")
    sink = logger.add(sys.stderr, format="{level} | {message}", colorize=False)
    try:
        return _export_json(args) if argv[0] == "export-json" else _convert_wem(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1
    finally:
        logger.remove(sink)
