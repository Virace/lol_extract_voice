"""根据 SVG logo 生成 PNG 与多尺寸 ICO 图标组。"""

from __future__ import annotations

import argparse
import shutil
import struct
import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ICO_EMBED_MAX_DIMENSION = 256


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        argparse.Namespace: 解析后的命令行参数。
    """
    parser = argparse.ArgumentParser(description="根据 SVG logo 生成 PNG 与多尺寸 ICO 图标组。")
    parser.add_argument(
        "--source-svg",
        default="src/lol_audio_unpack/gui/assets/app_icon.svg",
        help="源 SVG 图标路径。",
    )
    parser.add_argument(
        "--output-ico",
        default="src/lol_audio_unpack/gui/assets/app_icon.ico",
        help="输出 ICO 路径。",
    )
    parser.add_argument(
        "--output-png",
        default="src/lol_audio_unpack/gui/assets/app_icon.png",
        help="输出主 PNG 路径。",
    )
    parser.add_argument(
        "--output-png-256",
        default="src/lol_audio_unpack/gui/assets/app_icon_256.png",
        help="输出 256 PNG 路径。",
    )
    parser.add_argument(
        "--master-size",
        type=int,
        default=1024,
        help="主 PNG 导出的边长。",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[16, 24, 32, 40, 48, 64, 96, 128, 256],
        help="写入 ICO 图标组的尺寸列表。",
    )
    return parser.parse_args()


def resolve_repo_path(value: str, repo_root: Path) -> Path:
    """将相对路径解析到仓库根目录。

    Args:
        value: 用户提供的路径参数。
        repo_root: 仓库根目录。

    Returns:
        Path: 解析后的绝对路径。
    """
    path = Path(value)
    return path if path.is_absolute() else (repo_root / path).resolve()


def render_png(renderer: QSvgRenderer, path: Path, size: int) -> None:
    """把 SVG 渲染为指定尺寸 PNG。

    Args:
        renderer: 已初始化的 SVG 渲染器。
        path: 输出 PNG 路径。
        size: 输出边长。
    """
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0, 0, size, size))
    finally:
        painter.end()

    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path)):
        raise RuntimeError(f"保存 PNG 失败: {path}")


def build_ico(frames: list[tuple[int, bytes]], output_path: Path) -> None:
    """将多尺寸 PNG 帧封装为 ICO 图标组。

    Args:
        frames: ``(size, png_bytes)`` 列表。
        output_path: 输出 ICO 路径。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = bytearray()
    blobs = bytearray()
    offset = 6 + 16 * len(frames)

    for size, png_bytes in frames:
        dimension = 0 if size >= ICO_EMBED_MAX_DIMENSION else size
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(png_bytes),
                offset,
            )
        )
        blobs.extend(png_bytes)
        offset += len(png_bytes)

    output_path.write_bytes(header + entries + blobs)


def main() -> int:
    """执行图标资源生成流程。

    Returns:
        int: 进程退出码。
    """
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    source_svg = resolve_repo_path(args.source_svg, repo_root)
    output_ico = resolve_repo_path(args.output_ico, repo_root)
    output_png = resolve_repo_path(args.output_png, repo_root)
    output_png_256 = resolve_repo_path(args.output_png_256, repo_root)
    sizes = sorted(set(args.sizes))

    if not source_svg.is_file():
        raise FileNotFoundError(f"SVG 图标不存在: {source_svg}")

    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(source_svg))
    if not renderer.isValid():
        raise RuntimeError(f"SVG 无法渲染: {source_svg}")

    temp_dir = Path(tempfile.mkdtemp(prefix="icon-build-", dir=repo_root / ".temp"))
    try:
        render_png(renderer, output_png, args.master_size)
        render_png(renderer, output_png_256, 256)

        frames: list[tuple[int, bytes]] = []
        for size in sizes:
            frame_path = temp_dir / f"app_icon_{size}.png"
            render_png(renderer, frame_path, size)
            frames.append((size, frame_path.read_bytes()))

        build_ico(frames, output_ico)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        app.quit()

    print("已生成图标资源:")
    print(f"  SVG : {source_svg}")
    print(f"  PNG : {output_png}")
    print(f"  PNG : {output_png_256}")
    print(f"  ICO : {output_ico}")
    print("图标组尺寸: " + ", ".join(str(size) for size in sizes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
