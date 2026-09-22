"""内容对象、精确媒体引用及其索引合同。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

MAX_MEDIA_ID = 0xFFFFFFFF


class LibraryError(ValueError):
    """资源库数据或路径不满足合同，拒绝继续写入。"""


class LibraryBusyError(RuntimeError):
    """同一资源库已有写入任务。"""


def relative_path(value: str) -> str:
    """校验跨平台相对路径，统一使用正斜杠。

    Raises:
        LibraryError: 绝对路径、上级跳转或 Windows 非法路径片段。
    """
    if not isinstance(value, str):
        raise LibraryError("路径必须是字符串")
    text = value.replace("\\", "/")
    parts = text.split("/")
    if not text or any(
        not part or part in {".", ".."} or part.endswith((".", " ")) or any(char in part for char in ':<>"|?*\x00')
        for part in parts
    ):
        raise LibraryError(f"必须使用安全的相对路径: {value}")
    return text


def _comparison_path(path: PurePath) -> PurePath:
    """统一已解析 Windows 路径的盘符和 UNC 前缀，仅用于边界比较。"""
    if not isinstance(path, PureWindowsPath):
        return path
    drive = path.drive
    if drive.lower().startswith("\\\\?\\unc\\"):
        drive = "\\\\" + drive[8:]
    elif drive.startswith("\\\\?\\") and re.fullmatch("[a-zA-Z]:", drive[4:]):
        drive = drive[4:]
    else:
        return path
    return PureWindowsPath(drive + path.root, *path.parts[1:])


def resolve_path(root: Path, value: str) -> Path:
    """定位库内相对路径，拒绝经符号链接或 junction 逃出库根。"""
    path = root / PurePosixPath(relative_path(value))
    resolved = path.resolve()
    boundary = root.resolve()
    # resolve() 仍负责解析重解析点；Windows 可能只为一侧保留扩展前缀。
    # 仅统一比较格式，实际读写路径及越界检查均保留。
    if not _comparison_path(resolved).is_relative_to(_comparison_path(boundary)):
        raise LibraryError(f"路径超出资源库: {value}（实际路径: {resolved}，库根: {boundary}）")
    return path


def normalize_region(region: str) -> str:
    """将输入区域统一为语言小写、国家大写，default 表示 en_US。"""
    if region == "default":
        return "en_US"
    if not isinstance(region, str) or not re.fullmatch(r"[A-Za-z]{2}_[A-Za-z]{2}", region):
        raise LibraryError(f"无效区域代码: {region}")
    language, country = region.split("_")
    return f"{language.lower()}_{country.upper()}"


@dataclass(frozen=True)
class ObjectRef:
    """已完成原始 WEM 的完整摘要与字节数。"""

    digest: str
    size: int | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.digest, str) or not re.fullmatch(r"[0-9a-f]{64}", self.digest):
            raise LibraryError("对象摘要必须为完整小写 SHA-256")
        if self.size is not None and (type(self.size) is not int or self.size <= 0):
            raise LibraryError("对象必须包含正数字节")

    @property
    def path(self) -> str:
        """返回相对于库根的固定对象位置。"""
        return f"audios/_data/{self.digest[:2]}/{self.digest}.wem"


@dataclass(frozen=True)
class PublishedObject:
    """本次对象发布结果，新增与复用分别统计。"""

    ref: ObjectRef
    created: bool


@dataclass(frozen=True)
class MediaRef:
    """实体及皮肤内的原 WEM ID 与内容，不包含显示或事件信息。"""

    entity_type: str
    entity_id: str
    media_id: int
    object: ObjectRef
    skin_id: str | None = None

    def __post_init__(self) -> None:
        if self.entity_type not in {"champion", "map", "resource_pack"}:
            raise LibraryError("无效实体类型")
        if not isinstance(self.entity_id, str) or not self.entity_id:
            raise LibraryError("实体 ID 无效")
        if self.entity_type == "champion":
            if not isinstance(self.skin_id, str) or not self.skin_id.isdecimal():
                raise LibraryError("英雄媒体必须包含皮肤 ID")
        elif self.skin_id is not None:
            raise LibraryError("非英雄媒体没有皮肤 ID")
        if type(self.media_id) is not int or not 0 <= self.media_id <= MAX_MEDIA_ID:
            raise LibraryError("原媒体 ID 必须为 uint32")


@dataclass(frozen=True)
class WavRef:
    """一个固定输出位置当前保存的 WEM 内容和 WAV 格式。"""

    path: str
    digest: str
    format: str

    def __post_init__(self) -> None:
        ObjectRef(self.digest)
        object.__setattr__(self, "path", relative_path(self.path))
        if not self.path.startswith("wavs/") or not self.path.endswith(".wav"):
            raise LibraryError("WAV 输出必须位于 wavs 内")
        if self.format not in {"auto", "pcm16", "pcm24", "pcm32", "float"}:
            raise LibraryError("WAV 格式无效")


@dataclass(frozen=True)
class MergeResult:
    """一次成功归并的变化计数，不等同于累计库大小。"""

    added: int = 0
    updated: int = 0
    reused: int = 0
    written: bool = False
