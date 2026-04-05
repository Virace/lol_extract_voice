"""设置页路径卡片与文件对话框 helper。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFileDialog

from lol_audio_unpack.gui.common import format_default_relative_path


def apply_path_card_label(card, path: str, default: str = "") -> None:
    """将路径显示在卡片文案中。"""
    if path:
        card.setContent(f"当前: {format_default_relative_path(path)}")
    elif default:
        card.setContent(f"默认: {format_default_relative_path(default)}")
    else:
        card.setContent("当前: 未设置")


def pick_directory(
    *,
    host,
    title: str,
    current: str,
) -> str:
    """弹出目录选择对话框并返回结果。"""
    return QFileDialog.getExistingDirectory(
        host,
        title,
        current,
        QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
    )


def pick_file(
    *,
    host,
    title: str,
    current: str,
    file_filter: str,
) -> str:
    """弹出文件选择对话框并返回结果。"""
    path, _ = QFileDialog.getOpenFileName(host, title, current, file_filter)
    return path


def pick_and_apply_directory(  # noqa: PLR0913
    *,
    host,
    title: str,
    current: str,
    assign,
    save,
    card,
    default: str,
    changed_signal,
    emit_context_changed=None,
) -> None:
    """弹出目录选择并在成功后应用到配置与卡片。"""
    path = pick_directory(host=host, title=title, current=current)
    if not path:
        return
    assign(path)
    save()
    apply_path_card_label(card, path, default)
    changed_signal.emit(path)
    if emit_context_changed is not None:
        emit_context_changed()


def pick_and_apply_file(  # noqa: PLR0913
    *,
    host,
    title: str,
    current: str,
    file_filter: str,
    assign,
    save,
    card,
    default: str,
    changed_signal,
) -> None:
    """弹出文件选择并在成功后应用到配置与卡片。"""
    path = pick_file(host=host, title=title, current=current, file_filter=file_filter)
    if not path:
        return
    assign(path)
    save()
    apply_path_card_label(card, path, default)
    changed_signal.emit(path)
