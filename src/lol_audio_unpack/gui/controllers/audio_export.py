"""协调总览选择、导出核对和冻结请求，不在 UI 执行转码。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QModelIndex, QObject, QPoint, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox
from qfluentwidgets import Action, CheckBox, RoundMenu

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.app.audio_export import AudioExportRequest, ExportTarget
from lol_audio_unpack.app.audio_scope import AudioScope, MappingNode
from lol_audio_unpack.app.audio_selection import AudioSelection
from lol_audio_unpack.gui.view.overview.export_bar import AudioExportBar


class AudioExportController(QObject):
    """让两种预览模型共享单实体选择，并向全局执行器提交一次请求。"""

    export_requested = Signal(object)
    index_requested = Signal()

    def __init__(self, bar: AudioExportBar, tree, audio_list, *, parent=None) -> None:
        """绑定既有预览视图及其行末选择信号。"""
        super().__init__(parent)
        self.bar = bar
        self.tree = tree
        self.audio_list = audio_list
        self.selection = AudioSelection()
        self.request: AudioExportRequest | None = None
        self.mode = False
        self.busy = False
        self.index_complete = False
        self._available_count = 0
        self._audio_index_failed = False
        self._unavailable_count = 0
        tree.model().audio_selection = self.selection
        audio_list.source_model.audio_selection = self.selection
        tree.model().selection_changed.connect(self.refresh)
        audio_list.source_model.selection_changed.connect(self.refresh)
        tree.expanded.connect(self.refresh)
        tree.node_export_requested.connect(self._show_node_menu)
        bar.mode_button.clicked.connect(self.toggle_mode)
        bar.all_button.clicked.connect(self.select_all)
        bar.clear_button.clicked.connect(self.clear)
        bar.undo_button.clicked.connect(self.undo)
        bar.only_selected.toggled.connect(self.refresh)
        bar.export_button.clicked.connect(lambda: self.review_export())  # noqa: PLW0108 -- 丢弃 clicked 的布尔参数。

    def configure(
        self, request: AudioExportRequest, *, unavailable_count: int = 0, mapping_path: Path | None = None
    ) -> None:
        """记录当前实体的合法根目录和格式；同实体重载保留选择。"""
        old = self.request
        if old is None or (old.entity_type, old.entity_id, old.version, old.version_root) != (
            request.entity_type,
            request.entity_id,
            request.version,
            request.version_root,
        ):
            self.selection.reset()
            self.mode = False
            self.index_complete = False
            self._available_count = 0
            self._audio_index_failed = False
            self.bar.only_selected.setChecked(False)
        self.request = request
        self.tree.model().mapping_source = None
        if mapping_path is not None and mapping_path.is_file():
            stat = mapping_path.stat()
            self.tree.model().mapping_source = MappingNode(
                mapping_path, request.entity_type, request.entity_id, (stat.st_size, stat.st_mtime_ns)
            )
        self._unavailable_count = unavailable_count
        self.refresh()

    def reset(self) -> None:
        """上下文失效时清理不再可用的导出范围。"""
        self.selection.reset()
        self.request = None
        self.tree.model().mapping_source = None
        self.mode = False
        self.index_complete = False
        self._available_count = 0
        self._audio_index_failed = False
        self._unavailable_count = 0
        self.refresh()

    def confirm_change(self) -> bool:
        """切换实体前告知将清空范围，取消可继续留在原实体。"""
        if not self.selection.has_selection:
            return True
        dialog = QMessageBox(self.bar.window())
        dialog.setWindowTitle("切换预览对象")
        dialog.setText("切换对象将清空当前音频导出选择。")
        dialog.setInformativeText("左侧任务对象的勾选不受影响。")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Yes).setText("清空并切换")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("留在当前对象")
        return dialog.exec() == int(QMessageBox.StandardButton.Yes)

    def set_available(self, refs: tuple[AudioRef, ...], *, complete: bool) -> None:
        """应用已完成的路径索引，不把映射不可用叶子纳入选择。"""
        self._available_count = len({ref.path for ref in refs})
        self.selection.set_available(ref.path for ref in refs)
        self.index_complete = complete
        self._audio_index_failed = False
        self.refresh()

    def set_index_error(self, failed: bool = True) -> None:
        """记录全量目录索引失败状态，避免底部显示虚构总数。

        Args:
            failed: 是否进入索引失败状态。
        """
        self._audio_index_failed = bool(failed)
        if failed:
            self.index_complete = False
        self.refresh()

    def set_busy(self, busy: bool) -> None:
        """运行中保留浏览选择，阻止另起一批导出。"""
        self.busy = busy
        self.refresh()

    def toggle_mode(self) -> None:
        """进入或退出显式选择模式，退出不丢失选择。"""
        self.mode = not self.mode
        self.refresh()
        if self.mode and not self.index_complete:
            self.index_requested.emit()

    def select_all(self) -> None:
        """全选源目录，与搜索和当前展开状态无关。"""
        self.selection.select_all()
        self.refresh()

    def clear(self) -> None:
        """清空右侧音频选择。"""
        self.selection.clear()
        self.refresh()

    def undo(self) -> None:
        """撤销最后一次选择动作。"""
        self.selection.undo()
        self.refresh()

    def refresh(self, *_args) -> None:
        """同步选择工具与模型，保留现有树节点和索引。"""
        self.tree.model().selection_mode = self.mode
        self.audio_list.source_model.selection_mode = self.mode
        self.bar.set_mode(self.mode)
        self.bar.mode_button.setEnabled(self.request is not None and bool(self.request.targets))
        self.bar.undo_button.setEnabled(self.selection.can_undo)
        self.bar.clear_button.setEnabled(self.selection.has_selection)
        self.bar.export_button.setEnabled(self.selection.has_selection and not self.busy)
        self.bar.export_button.setToolTip("已有任务运行，请等待完成" if self.busy else "")
        count = self.selection.count
        if self.index_complete:
            selection_text = f"已选 {count:,} / {self._available_count:,} 个文件"
        elif self._audio_index_failed:
            selection_text = f"已选 {count:,} 个文件 · 目录索引失败"
        else:
            selection_text = f"已选 {count:,} 个文件 · 目录总数待确认"
        self.bar.selection_count.setText(selection_text)
        if not self.mode and not self.bar.summary.text() and self.request is not None:
            self.bar.summary.setText(
                f"全部音频 {self._available_count:,} 个文件" if self.index_complete else "正在索引全部音频…"
            )
        only_selected = self.mode and self.bar.only_selected.isChecked()
        self.tree.refresh_export_selection(only_selected=only_selected)
        self.audio_list.refresh_export_selection(only_selected=only_selected)

    def _show_node_menu(self, index: QModelIndex, position: QPoint) -> None:
        menu = RoundMenu(parent=self.bar)
        action = Action("导出此节点下的音频…", menu)
        action.setEnabled(not self.busy and self.request is not None)
        action.triggered.connect(
            lambda: self.review_export(
                self.tree.model().selection_paths(index), node=self.tree.model().scope_node(index)
            )
        )
        menu.addAction(action)
        menu.exec(position)

    def review_export(self, paths: frozenset[Path] | None = None, *, node: MappingNode | None = None) -> None:
        """以目录摘要核对一次性导出，确认后只发送冻结描述。"""
        request = self.request
        if request is None or self.busy:
            return
        selection = self.selection
        if paths is not None:
            selection = AudioSelection()
            selection.set_available(paths)
            if node is not None:
                selection.set_node(node, paths, True)
            else:
                selection.set_paths(paths, True)
        roots = tuple(target.scope.root for target in request.targets)
        prefixes = {}
        for root in roots:
            parts = root.relative_to(request.version_root).parts
            prefixes[root] = parts[0] if parts and parts[0] in {"VO", "SFX", "MUSIC"} else ""
        scopes = selection.build_scopes(roots, prefixes=prefixes)
        if not scopes:
            return
        output_text = QFileDialog.getExistingDirectory(self.bar.window(), "选择 WAV 导出目录")
        if not output_text:
            return
        output = Path(output_text)
        targets = tuple(ExportTarget(scope, output / self._output_prefix(scope.root)) for scope in scopes)
        dialog = QMessageBox(self.bar.window())
        dialog.setWindowTitle("核对音频导出")
        dialog.setText(f"{request.entity_name} · WAV ({request.options.format})")
        scope_text = "当前实体目录全部 WEM" if selection.state.all_selected else f"所选 {selection.count:,} 个音频"
        exclusions = len(selection.state.excluded)
        if exclusions:
            scope_text += f"，排除 {exclusions:,} 个"
        dialog.setInformativeText(
            f"范围：{scope_text}\n源目录："
            + "\n".join(str(scope.root) for scope in scopes)
            + f"\n输出：{output}\n保留目录结构与原始 ID。\n已知可用 {selection.count:,} 个；最终目录数量在后台扫描时复核。"
            + f"\n对应文件不可用的映射项 {self._unavailable_count:,} 个，本次不会自动解包。"
        )
        overwrite = CheckBox("覆盖本次范围内的已有 WAV（默认跳过）", dialog)
        dialog.setCheckBox(overwrite)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Ok).setText("开始导出")
        dialog.button(QMessageBox.StandardButton.Cancel).setText("返回选择")
        if dialog.exec() == int(QMessageBox.StandardButton.Ok):
            self.export_requested.emit(replace(request, targets=targets, overwrite=overwrite.isChecked()))

    def _output_prefix(self, root: Path) -> str:
        """按现有按类型分目录布局保留逻辑路径，不用实体显示名拼路径。"""
        if self.request is None or len(self.request.targets) == 1:
            return ""
        parts = root.relative_to(self.request.version_root).parts
        return parts[0] if parts and parts[0] in {"VO", "SFX", "MUSIC"} else "lobby"

    def export_file(self, source: Path, output: Path, *, overwrite: bool, reveal: bool = False) -> None:
        """单文件另存为也进入共用执行器，不阻塞 UI 线程。"""
        request = self.request
        if request is None or self.busy:
            return
        root = next((target.scope.root for target in request.targets if source.is_relative_to(target.scope.root)), None)
        if root is None:
            raise ValueError("当前文件不属于已确认的实体目录")
        scope = AudioScope(root, files=(source.relative_to(root).as_posix(),))
        self.export_requested.emit(
            replace(
                request,
                targets=(ExportTarget(scope, output.parent),),
                output_file=output,
                overwrite=overwrite,
                reveal_output=reveal,
            )
        )
