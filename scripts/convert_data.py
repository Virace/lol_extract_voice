"""显式离线转换 MessagePack、JSON 与 YAML，不迁移 schema 或覆盖已有文件。"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from io import StringIO
from pathlib import Path

import msgpack
from ruamel.yaml import YAML


def validate_value(value: object, *, json_output: bool = False, parents: frozenset[int] = frozenset()) -> None:
    """拒绝不能在项目数据类型间无损转换的值与循环引用。"""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is bytes:
        if json_output:
            raise ValueError("JSON 无法无损表示二进制值，请使用 YAML")
        return
    if type(value) not in (dict, list):
        raise ValueError(f"不支持无损转换的数据类型: {type(value).__name__}")
    if id(value) in parents:
        raise ValueError("不支持循环引用")
    parents = parents | {id(value)}
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) not in (str, int):
                raise ValueError("字典键只支持字符串和整数")
            if json_output and type(key) is not str:
                raise ValueError("JSON 无法保留整数键类型，请使用 YAML")
            validate_value(child, json_output=json_output, parents=parents)
    else:
        for child in value:
            validate_value(child, json_output=json_output, parents=parents)


def build_mapping(pairs: list[tuple[object, object]]) -> dict:
    """拒绝会在构造字典时丢失数据的重复键。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复字典键: {key!r}")
        result[key] = value
    return result


def convert(source: Path, target: Path, *, source_format: str, target_format: str) -> Path:
    """转换一个文件并原子发布，保留源文件和已有目标。

    Args:
        source: 必须存在的输入文件。
        target: 尚不存在的输出文件。
        source_format: 显式输入格式，msgpack、json、yaml 或 yml。
        target_format: 显式输出格式，与输入格式使用相同名称。

    Returns:
        成功发布的输出路径。

    Raises:
        ValueError: 格式、结构或类型无法无损转换。
        OSError: 输入不可读、目标存在或写入失败。
    """
    if source.resolve() == target.resolve() or target.exists():
        raise FileExistsError(f"不覆盖输入或已有目标: {target}")
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    if source_format == "msgpack":
        value = msgpack.unpackb(source.read_bytes(), raw=False, strict_map_key=False, object_pairs_hook=build_mapping)
    elif source_format == "json":
        value = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=build_mapping)
    elif source_format in ("yaml", "yml"):
        value = yaml.load(source.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"不支持的输入格式: {source_format}")
    validate_value(value, json_output=target_format == "json")
    if target_format == "msgpack":
        payload = msgpack.packb(value, use_bin_type=True)
    elif target_format == "json":
        payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    elif target_format in ("yaml", "yml"):
        stream = StringIO()
        yaml.dump(value, stream)
        payload = stream.getvalue().encode("utf-8")
    else:
        raise ValueError(f"不支持的输出格式: {target_format}")

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    scratch = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # 同目录硬链接只发布完整文件，并在目标并发出现时失败，避免 replace 覆盖用户文件。
        os.link(scratch, target)
    finally:
        scratch.unlink()
    return target


def main() -> int:
    """执行独立离线转换命令并输出明确的失败原因。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    formats = ("msgpack", "json", "yaml", "yml")
    parser.add_argument("--from", dest="source_format", required=True, choices=formats)
    parser.add_argument("--to", dest="target_format", required=True, choices=formats)
    args = parser.parse_args()
    try:
        result = convert(args.input, args.output, source_format=args.source_format, target_format=args.target_format)
    except Exception as exc:
        parser.exit(1, f"转换失败: {exc}\n")
    print(f"已转换: {result}（仅转换容器格式，不升级 schema）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
