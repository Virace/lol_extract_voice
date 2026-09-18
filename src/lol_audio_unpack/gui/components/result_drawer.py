"""任务结果右侧覆盖面板，独立滚动且不进入主路由。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QEasingCurve,
    QEvent,
    QModelIndex,
    QPoint,
    Qt,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QStyle,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SubtitleLabel,
    TableView,
    TreeWidget,
    isDarkTheme,
)

from lol_audio_unpack.app.failures import TaskFailure
from lol_audio_unpack.app.results import ResultStatus
from lol_audio_unpack.config import SettingKey
from lol_audio_unpack.gui.common.styles import get_fluent_frame_stroke_pair
from lol_audio_unpack.gui.task_models import ExecutionTaskResult, QueuedExecutionTask

_STAGES = {"update": "数据更新", "extract": "音频解包", "wav": "WAV 转码", "mapping": "事件映射", "run": "执行过程"}
_STATUSES = {
    ResultStatus.SUCCESS: "完成",
    ResultStatus.PARTIAL: "部分完成",
    ResultStatus.FAILED: "失败",
    ResultStatus.CANCELLED: "已取消",
}
_UNITS = {
    "file": "文件",
    "container": "容器（音频数未知）",
    "entity": "实体",
    "stage": "阶段",
    "unknown": "完成范围未知",
}
_EMPTY_INDEX = QModelIndex()
_SLIDE_DURATION_MS = 220
_AUDIO_TYPES = {"VO": "语音（VO）", "SFX": "音效（SFX）", "MUSIC": "音乐（MUSIC）"}


class FailureTableModel(QAbstractTableModel):
    """直接引用结构化失败记录，不为大量失败行实例化控件。"""

    def __init__(self, parent=None) -> None:
        """初始化空失败表。"""
        super().__init__(parent)
        self.issues: tuple[TaskFailure, ...] = ()

    def set_issues(self, issues: tuple[TaskFailure, ...]) -> None:
        """替换当前结果视图的数据引用。"""
        self.beginResetModel()
        self.issues = issues
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = _EMPTY_INDEX) -> int:
        """返回真实失败记录数量。"""
        return 0 if parent.isValid() else len(self.issues)

    def columnCount(self, parent: QModelIndex = _EMPTY_INDEX) -> int:
        """返回状态、对象、步骤和单位四列。"""
        return 4

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        """用精确单位与解决状态呈现失败项。"""
        if not index.isValid() or not 0 <= index.row() < len(self.issues):
            return None
        issue = self.issues[index.row()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return issue.error
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                "已解决" if issue.resolved else "待处理",
                issue.label,
                _STAGES.get(issue.stage, issue.stage),
                _UNITS.get(issue.unit, issue.unit),
            )[index.column()]
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)):
        """提供固定列名。"""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("状态", "对象 / 文件", "步骤", "单位")[section]
        return None


class ResultDrawer(QDialog):
    """覆盖当前窗口的模态详情层，阻止误点背后表单并支持 Escape。"""

    retry_requested = Signal(object)

    def __init__(self, parent: QWidget) -> None:
        """建立右侧面板，主窗口几何改变时保持覆盖关系。"""
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("本次任务结果")
        parent.installEventFilter(self)
        self.panel = QFrame(self)
        self.panel.setObjectName("TaskResultPanel")
        self._slide_position = 0.0
        self._panel_snapshot: QPixmap | None = None
        self._closing_result: int | None = None
        self._slide = QVariantAnimation(self)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.valueChanged.connect(self._move_panel)
        self._slide.finished.connect(self._finish_slide)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(20, 16, 20, 16)
        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("本次任务结果", self.panel), 1)
        self.close_button = PushButton("关闭", self.panel)
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        panel_layout.addLayout(header)
        self.scroll = ScrollArea(self.panel)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("TaskResultContent")
        self.scroll.setWidget(self.content)
        panel_layout.addWidget(self.scroll, 1)
        body = QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(12)
        self.summary = BodyLabel(self.content)
        self.summary.setWordWrap(True)
        body.addWidget(self.summary)
        self.snapshot = CaptionLabel(self.content)
        self.snapshot.setWordWrap(True)
        self.snapshot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.addWidget(self.snapshot)
        self.stages = TreeWidget(self.content)
        self.stages.setHeaderLabels(("阶段 / 对象", "结果", "本次产出"))
        self.stages.setRootIsDecorated(True)
        self.stages.setUniformRowHeights(True)
        self.stages.setMinimumHeight(240)
        self.stages.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stages.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stages.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        body.addWidget(self.stages, 1)
        self.issue_summary = BodyLabel(self.content)
        body.addWidget(self.issue_summary)
        self.table = TableView(self.content)
        self.model = FailureTableModel(self.table)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 84)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 120)
        self.table.setMinimumHeight(180)
        self.table.setMaximumHeight(270)
        body.addWidget(self.table)
        self.detail = PlainTextEdit(self.content)
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(130)
        self.detail.setMaximumHeight(230)
        self.detail.setAccessibleName("失败原因与诊断")
        body.addWidget(self.detail)
        self.table.selectionModel().selectionChanged.connect(self._show_issue)
        actions = QHBoxLayout()
        self.report_button = PushButton("打开报告", self.panel)
        self.output_button = PushButton("打开产物目录", self.panel)
        actions.addWidget(self.report_button)
        actions.addWidget(self.output_button)
        panel_layout.addLayout(actions)
        retry_actions = QHBoxLayout()
        self.retry_selected_button = PushButton("核对所选重试…", self.panel)
        self.retry_all_button = PrimaryPushButton("核对全部失败重试…", self.panel)
        retry_actions.addWidget(self.retry_selected_button)
        retry_actions.addWidget(self.retry_all_button)
        panel_layout.addLayout(retry_actions)
        self.retry_selected_button.clicked.connect(self._retry_selected)
        self.retry_all_button.clicked.connect(self._retry_all)
        self.report_button.clicked.connect(self._open_report)
        self.output_button.clicked.connect(self._open_output)
        self._result: ExecutionTaskResult | None = None
        self._busy = False
        self._sync_geometry()

    def set_result(
        self,
        task: QueuedExecutionTask,
        result: ExecutionTaskResult,
        issues: tuple[TaskFailure, ...],
        *,
        attempts: int,
        history: tuple[ExecutionTaskResult, ...] = (),
    ) -> None:
        """使用执行快照展示结果；重试后原失败与已解决状态仍可核对。"""
        self._result = result
        self._history = history or (result,)
        pending = sum(not issue.resolved for issue in issues)
        resolved = len(issues) - pending
        self.summary.setText(f"{result.summary}\n{task.draft.source_summary}")
        params = task.draft.task_params
        request = task.draft.export_request
        scope = "、".join(params.selected_steps())
        if request is not None:
            scope = "WAV 导出 · " + (
                "当前实体目录" if any(target.scope.directories for target in request.targets) else "所选音频"
            )
        paths = "\n".join(str(target.output_root) for target in request.targets) if request is not None else ""
        if request is None:
            paths = str(task.draft.context_input.to_settings().get(SettingKey.OUTPUT_PATH) or "默认 output 目录")
        options = (
            f"转码并发 {request.options.worker_count} · 已有输出{'覆盖' if request.overwrite else '跳过'}"
            if request
            else f"并发 {params.max_workers} · 转码并发 {params.wav_workers} · "
            f"附加 BP 语音{'开启' if params.with_bp_vo else '关闭'} · "
            f"数据整合{'开启' if params.integrate_data else '关闭'}"
        )
        if request is not None:
            excluded = sum(len(target.scope.excluded) for target in request.targets)
            node_count = sum(len(target.scope.nodes) for target in request.targets)
            file_count = sum(len(target.scope.files) for target in request.targets)
            directory_count = sum(len(target.scope.directories) for target in request.targets)
            ranges = []
            if directory_count:
                ranges.append(f"{directory_count} 个源目录")
            if node_count:
                ranges.append(f"{node_count} 个映射节点")
            if file_count:
                ranges.append(f"{file_count} 个精确文件")
            ranges.append(f"排除 {excluded} 个文件")
            options += "\n范围：" + " · ".join(ranges)
        audio_types = "、".join(label for key, label in _AUDIO_TYPES.items() if key not in params.exclude_types)
        self.snapshot.setText(
            f"版本：{result.version or task.draft.version or '未确认'}\n动作：{scope}"
            + (f"\n解包类型：{audio_types or '无'}" if request is None and params.run_extract else "")
            + (
                f"\nWAV 格式：{request.options.format if request else params.wav_format}"
                if request or params.wav_enabled
                else ""
            )
            + (f"\n输出：{paths}" if paths else "")
            + (f"\n已执行 {attempts} 次手动重试；原始结果和各次报告分别保存。" if attempts else "")
            + ("\n本次执行报告未保存，当前详情仍保留执行事实。" if result.report_path is None else "")
        )
        self.snapshot.setToolTip(options)
        self.stages.clear()
        for attempt, stage in (
            (attempt, stage) for attempt, item in enumerate(self._history) for stage in item.run_result.stages
        ):
            prefix = ("原始执行 · " if attempt == 0 else f"重试 {attempt} · ") if len(self._history) > 1 else ""
            label = prefix + _STAGES.get(stage.stage, stage.stage)
            row = QTreeWidgetItem((label, _STATUSES[stage.status]))
            row.setToolTip(0, stage.note or stage.error_message or "")
            self.stages.addTopLevelItem(row)
            if stage.note:
                QTreeWidgetItem(row, (stage.note, ""))
            if stage.entities and stage.stage != "wav":
                for entity in stage.entities:
                    name = entity.entity_name or str(entity.entity_id)
                    artifacts = set(entity.artifacts)
                    if stage.stage == "extract":
                        output = f"{sum(Path(path).suffix.lower() == '.wem' for path in artifacts):,} 个 WEM"
                    else:
                        output = (
                            f"{len(artifacts):,} 份映射" if stage.stage == "mapping" else f"{len(artifacts):,} 个产物"
                        )
                    child = QTreeWidgetItem(row, (name, _STATUSES[entity.status], output))
                    child.setToolTip(0, entity.error_message or "")
            if stage.stage == "wav":
                for batch in stage.wav_batches:
                    child = QTreeWidgetItem(
                        row,
                        (
                            batch.output_root.name,
                            _STATUSES[ResultStatus(batch.status)],
                            f"{batch.success_count:,} 个 WAV · 跳过 {batch.skipped_count:,}",
                        ),
                    )
                    child.setToolTip(0, str(batch.output_root))
            row.setExpanded(True)
        self.issue_summary.setText(
            f"失败记录：待处理 {pending} 项 · 已解决 {resolved} 项（单位见各行）" if issues else "无失败记录"
        )
        self.model.set_issues(issues)
        self.table.setFixedHeight(min(250, 44 + 36 * min(len(issues), 6)))
        self.table.setVisible(bool(issues))
        self.detail.setVisible(bool(issues))
        self.retry_selected_button.setVisible(pending > 0)
        self.retry_all_button.setVisible(pending > 0)
        self.report_button.setEnabled(result.report_path is not None)
        self._output_paths = tuple(
            dict.fromkeys(
                [
                    Path(path)
                    for item in self._history
                    for stage in item.run_result.stages
                    for entity in stage.entities
                    for path in entity.artifacts
                ]
                + [
                    batch.output_file or batch.output_root
                    for item in self._history
                    for batch in item.wav_batches
                    if batch.success_count or batch.skipped_count
                ]
            )
        )
        self.output_button.setEnabled(bool(self._output_paths))
        if issues:
            self.table.selectRow(next((index for index, issue in enumerate(issues) if not issue.resolved), 0))
        self.set_busy(self._busy)

    def set_busy(self, busy: bool) -> None:
        """禁止在运行过程中重复提交重试，详情仍可阅读。"""
        self._busy = busy
        retryable = any(
            not issue.resolved and issue.retry_mode not in {"none", "diagnostics"} for issue in self.model.issues
        )
        self.retry_all_button.setEnabled(not busy and retryable)
        self.retry_selected_button.setEnabled(not busy and retryable)
        hint = "已有任务运行，请等待完成" if busy else "先核对实际处理范围，再开始重试"
        self.retry_all_button.setToolTip(hint)
        self.retry_selected_button.setToolTip(hint)
        if self._panel_snapshot is not None:
            self._capture_panel()

    def _show_issue(self, *_args) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.detail.clear()
            return
        issue = self.model.issues[rows[0].row()]
        self.detail.setPlainText(
            f"{issue.label}\n步骤：{_STAGES.get(issue.stage, issue.stage)} · 单位：{_UNITS.get(issue.unit, issue.unit)}\n"
            f"原因：{issue.error}\n{issue.guidance}"
            + (f"\n来源：{issue.source_path}" if issue.source_path else "")
            + (f"\n输出：{issue.output_path}" if issue.output_path else "")
            + (
                f"\nWAD：{issue.detail.wad}\nEntry：{issue.detail.entry_hash}"
                if issue.detail and issue.detail.wad
                else ""
            )
        )

    def _retry_selected(self) -> None:
        self.retry_requested.emit(
            tuple(self.model.issues[index.row()] for index in self.table.selectionModel().selectedRows())
        )

    def _retry_all(self) -> None:
        self.retry_requested.emit(tuple(issue for issue in self.model.issues if not issue.resolved))

    def _open_report(self) -> None:
        if self._result is not None and self._result.report_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._result.report_path)))

    def _open_output(self) -> None:
        if self._result is None:
            return
        path = next(iter(self._output_paths), None)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    def showEvent(self, event) -> None:
        """每次打开按当前窗口和主题显示。"""
        self._sync_geometry()
        background = "rgb(28, 31, 38)" if isDarkTheme() else "rgb(255, 255, 255)"
        border = get_fluent_frame_stroke_pair()[int(isDarkTheme())]
        self.panel.setStyleSheet(
            f"QFrame#TaskResultPanel {{ background-color: {background}; border: 1px solid {border}; }}"
            "QWidget#TaskResultContent { background-color: transparent; }"
        )
        super().showEvent(event)
        self.close_button.setFocus()
        self._closing_result = None
        self._move_panel(0.0)
        self._animate_to(1.0)

    def done(self, result: int) -> None:
        """滑出结束后再关闭模态层，保持 Escape、按钮和遮罩的生命周期一致。"""
        if not self.isVisible():
            super().done(result)
            return
        if self._closing_result is not None:
            return
        self._closing_result = result
        self._animate_to(0.0)

    def _animate_to(self, position: float) -> None:
        """从当前进度衔接开关动画，并服从平台样式的动画开关。"""
        self._slide.stop()
        enabled = self.style().styleHint(QStyle.StyleHint.SH_Widget_Animation_Duration, None, self) > 0
        if not enabled:
            self._move_panel(position)
            self._finish_slide()
            return
        # 动画只搬运当前像素，避免半透明窗口移动时让整棵树和文字逐帧重绘。
        if self._panel_snapshot is None:
            self._capture_panel()
        self.panel.hide()
        self._slide.setDuration(_SLIDE_DURATION_MS)
        self._slide.setStartValue(self._slide_position)
        self._slide.setEndValue(position)
        self._slide.start()

    def _capture_panel(self) -> None:
        """在内容或尺寸变化后获取完整面板，快照只存活于本次开关动画。"""
        self.panel.ensurePolished()
        self.panel.layout().activate()
        self.content.layout().activate()
        self.stages.doItemsLayout()
        self._panel_snapshot = self.panel.grab()

    def _move_panel(self, position: float) -> None:
        self._slide_position = float(position)
        if self._panel_snapshot is None:
            self.panel.move(self.width() - round(self.panel.width() * self._slide_position), 0)
        self.update()

    def _finish_slide(self) -> None:
        self._panel_snapshot = None
        self._move_panel(self._slide_position)
        self.panel.show()
        if self._closing_result is not None:
            result = self._closing_result
            self._closing_result = None
            super().done(result)
        else:
            self.close_button.setFocus()

    def _sync_geometry(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.move(host.mapToGlobal(QPoint(0, 0)))
        self.resize(host.size())
        self.panel.resize(min(760, max(1, self.width())), self.height())
        if self._panel_snapshot is not None:
            self._capture_panel()
        self._move_panel(self._slide_position)

    def eventFilter(self, watched, event) -> bool:
        """保持叠层与父窗口同步，不参与主页面布局。"""
        if watched is self.parentWidget() and event.type() in {QEvent.Type.Resize, QEvent.Type.Move}:
            self._sync_geometry()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        """绘制用于明确模态作用域的半透明遮罩。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(55 * self._slide_position)))
        if self._panel_snapshot is not None:
            left = self.width() - round(self.panel.width() * self._slide_position)
            painter.drawPixmap(left, 0, self._panel_snapshot)

    def mousePressEvent(self, event) -> None:
        """点击遮罩只关闭详情，不把点击交给背后表单。"""
        left = self.width() - round(self.panel.width() * self._slide_position)
        if not self.panel.rect().translated(left, 0).contains(event.position().toPoint()):
            self.reject()
            return
        super().mousePressEvent(event)
