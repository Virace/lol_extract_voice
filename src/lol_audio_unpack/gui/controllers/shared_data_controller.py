"""共享实体数据加载与刷新的后台控制器。"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

from lol_audio_unpack.gui.controllers.contracts import (
    EntityRowsPayload,
    GuiNotice,
    RuntimeLoggingConfig,
    SharedDataLoadingState,
)
from lol_audio_unpack.gui.task_models import OutputStateRefreshRequest

SHARED_CONTEXT_BUILD_TIMEOUT_MS = 15000


def build_shared_entity_reader_signature(cfg) -> tuple[str | bool, ...]:
    """构建影响共享实体数据读取上下文的配置签名。"""
    overrides = cfg.to_app_context_overrides()
    return (
        overrides["SOURCE_MODE"],
        overrides["GAME_PATH"],
        overrides["GAME_REGION"],
        overrides["REMOTE_LIVE_REGION"],
        overrides["REMOTE_VERSION"],
        overrides["REMOTE_LCU_MANIFEST_URL"],
        overrides["REMOTE_GAME_MANIFEST_URL"],
    )


def build_shared_entity_scan_signature(cfg) -> tuple[str | bool, ...]:
    """构建仅影响输出扫描结果的配置签名。"""
    overrides = cfg.to_app_context_overrides()
    return (
        overrides["OUTPUT_PATH"],
        overrides["GROUP_BY_TYPE"],
    )


def build_shared_context_loading_message(cfg) -> str:
    """根据当前模式生成首页共享数据加载阶段文案。"""
    if getattr(cfg, "source_mode", "local_path") != "remote_snapshot":
        return "正在读取本地共享数据…"

    if getattr(cfg, "remote_snapshot_strategy", "latest") == "custom":
        return "正在校验固定远端快照…"

    return "正在解析最新远端版本…"


def build_shared_context_timeout_message(cfg) -> str:
    """根据当前模式生成共享数据加载超时提示。"""
    if cfg is None or getattr(cfg, "source_mode", "local_path") != "remote_snapshot":
        return "读取共享数据超时，请重试。"

    if getattr(cfg, "remote_snapshot_strategy", "latest") == "custom":
        return "校验固定远端快照超时，请检查配置后重试。"

    return "解析最新远端版本超时，请检查网络连接后重试。"


class SharedDataController(QObject):
    """负责共享实体数据主线的状态机与后台编排。"""

    loading_state_changed = Signal(object)
    app_context_changed = Signal(object)
    shared_data_cleared = Signal()
    entity_data_replaced = Signal(object)
    entity_rows_updated = Signal(object)
    notice_requested = Signal(object)
    reconfigure_runtime_logging_requested = Signal(object)

    def __init__(  # noqa: PLR0913
        self,
        *,
        get_config: Callable[[], object],
        has_incomplete_tasks: Callable[[], bool],
        create_app_context_fn: Callable[..., object],
        data_load_worker_cls,
        task_worker_cls,
        entity_data_loader_cls,
        start_worker_fn: Callable[[object], None],
        prepare_shared_entity_data_fn: Callable[[dict[str, str | bool]], None],
        reset_data_reader_singleton_fn: Callable[[], None],
        app_context_block_reason_fn: Callable[[object], str | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._get_config = get_config
        self._has_incomplete_tasks = has_incomplete_tasks
        self._create_app_context = create_app_context_fn
        self._data_load_worker_cls = data_load_worker_cls
        self._task_worker_cls = task_worker_cls
        self._entity_data_loader_cls = entity_data_loader_cls
        self._start_worker = start_worker_fn
        self._prepare_shared_entity_data = prepare_shared_entity_data_fn
        self._reset_data_reader_singleton = reset_data_reader_singleton_fn
        self._get_app_context_block_reason = app_context_block_reason_fn

        self.data_app_context = None
        self.is_loading_shared_data = False
        self.is_preparing_shared_data = False
        self.pending_refresh_notice = False
        self.pending_runtime_entity_refresh = False
        self.pending_runtime_entity_refresh_allow_auto_prepare = False
        self.pending_runtime_entity_refresh_reset_reader = False
        self.allow_auto_prepare_on_shared_reload = True
        self.shared_data_auto_prepare_attempted = False
        self.shared_data_prepare_worker = None
        self.shared_context_build_worker = None
        self.shared_context_build_cfg = None
        self.shared_context_build_request_id = 0
        self.shared_entity_reader_signature: tuple[str | bool, ...] | None = None
        self.shared_entity_scan_signature: tuple[str | bool, ...] | None = None

        self.runtime_entity_refresh_timer = QTimer(self)
        self.runtime_entity_refresh_timer.setSingleShot(True)
        self.runtime_entity_refresh_timer.setInterval(900)
        self.runtime_entity_refresh_timer.timeout.connect(self.flush_pending_runtime_entity_refresh)

        self.shared_context_build_timeout_timer = QTimer(self)
        self.shared_context_build_timeout_timer.setSingleShot(True)
        self.shared_context_build_timeout_timer.setInterval(SHARED_CONTEXT_BUILD_TIMEOUT_MS)
        self.shared_context_build_timeout_timer.timeout.connect(self.on_shared_context_build_timeout)

    def bootstrap(self, cfg=None) -> None:
        """初始化共享数据签名，并决定是否执行首轮加载。"""
        current_cfg = cfg or self._get_config()
        self.shared_entity_reader_signature = build_shared_entity_reader_signature(current_cfg)
        self.shared_entity_scan_signature = build_shared_entity_scan_signature(current_cfg)

        block_reason = self._get_app_context_block_reason(current_cfg)
        if block_reason is not None:
            logger.info(f"共享实体数据首轮加载已跳过: {block_reason}")
            self._apply_blocked_state(block_reason)
            return

        logger.debug("准备触发首轮共享实体数据加载")
        self.load_initial_data(current_cfg)

    def set_queue_busy(self, busy: bool) -> None:
        """在任务队列忙碌状态变化时暂停或恢复待处理刷新。"""
        if busy:
            self.runtime_entity_refresh_timer.stop()
            return
        self.flush_pending_runtime_entity_refresh()

    def load_initial_data(self, cfg=None) -> None:
        """程序启动或重载时加载共享实体数据。"""
        current_cfg = cfg or self._get_config()
        logger.info("开始加载共享实体数据")
        block_reason = self._get_app_context_block_reason(current_cfg)
        if block_reason is not None:
            logger.info(f"共享实体数据加载已跳过: {block_reason}")
            self._apply_blocked_state(block_reason)
            return

        self.is_loading_shared_data = True
        self.shared_context_build_request_id += 1
        current_request_id = self.shared_context_build_request_id
        self.shared_context_build_cfg = current_cfg
        self.loading_state_changed.emit(
            SharedDataLoadingState(
                message=build_shared_context_loading_message(current_cfg),
                active=True,
            )
        )

        if getattr(current_cfg, "source_mode", "local_path") == "remote_snapshot":
            strategy = getattr(current_cfg, "remote_snapshot_strategy", "latest")
            if strategy == "custom":
                logger.debug(
                    "当前配置: source_mode=remote_snapshot, strategy=custom, "
                    f"version={getattr(current_cfg, 'snapshot_version', '')}, output_path={current_cfg.output_path}"
                )
            else:
                logger.debug(
                    "当前配置: source_mode=remote_snapshot, strategy=latest, "
                    f"live_region={getattr(current_cfg, 'remote_live_region', '')}, output_path={current_cfg.output_path}"
                )
        else:
            logger.debug(
                "当前配置: source_mode=local_path, "
                f"output_path={current_cfg.output_path}, game_path={current_cfg.game_path}"
            )

        worker = self._task_worker_cls(
            lambda: self._create_app_context(cli_overrides=current_cfg.to_app_context_overrides())
        )
        worker.signals.finished.connect(
            lambda app_context, request_id=current_request_id: self.on_shared_context_build_finished(
                request_id, app_context
            )
        )
        worker.signals.failed.connect(
            lambda error, request_id=current_request_id: self.on_shared_context_build_failed(request_id, error)
        )
        self.shared_context_build_worker = worker
        self.shared_context_build_timeout_timer.start()
        self._start_worker(worker)

    def on_shared_context_build_finished(self, request_id: int, app_context) -> None:
        """共享 AppContext 后台构建完成后，继续实体扫描流程。"""
        if request_id != self.shared_context_build_request_id:
            return

        self.shared_context_build_timeout_timer.stop()
        self.shared_context_build_worker = None
        self.shared_context_build_cfg = None
        self.data_app_context = app_context
        self.app_context_changed.emit(self.data_app_context)
        self.shared_data_cleared.emit()
        logger.debug("共享数据 AppContext 创建成功")
        self.loading_state_changed.emit(
            SharedDataLoadingState(message="正在扫描英雄数据…", active=True)
        )
        logger.debug("准备启动 champions 实体状态扫描线程")
        self._champions_worker = self._data_load_worker_cls(self.data_app_context, "champions")
        self._champions_worker.finished.connect(self.on_champions_loaded)
        self._champions_worker.error.connect(self.on_data_load_error)
        self._champions_worker.start()

    def on_shared_context_build_failed(self, request_id: int, error: str) -> None:
        """处理共享 AppContext 后台构建失败。"""
        if request_id != self.shared_context_build_request_id:
            return

        self.shared_context_build_timeout_timer.stop()
        self.shared_context_build_worker = None
        self.shared_context_build_cfg = None
        self.is_loading_shared_data = False
        self.data_app_context = None
        self.app_context_changed.emit(None)
        self.shared_data_cleared.emit()
        logger.error(f"创建 AppContext 失败: {error}")
        self.loading_state_changed.emit(
            SharedDataLoadingState(message=f"加载失败: {error}", active=False)
        )
        if self.pending_refresh_notice:
            self.notice_requested.emit(
                GuiNotice(title="刷新失败", content=error, level="error")
            )
            self.pending_refresh_notice = False

    def on_shared_context_build_timeout(self) -> None:
        """处理共享 AppContext 后台构建超时。"""
        if self.shared_context_build_worker is None:
            return

        timeout_cfg = self.shared_context_build_cfg
        timeout_message = build_shared_context_timeout_message(timeout_cfg)
        self.shared_context_build_request_id += 1
        self.shared_context_build_worker = None
        self.shared_context_build_cfg = None
        self.is_loading_shared_data = False
        self.data_app_context = None
        self.app_context_changed.emit(None)
        self.shared_data_cleared.emit()
        logger.error(f"共享数据加载超时: {timeout_message}")
        self.loading_state_changed.emit(
            SharedDataLoadingState(message=f"加载失败: {timeout_message}", active=False)
        )
        self.notice_requested.emit(
            GuiNotice(title="共享数据加载超时", content=timeout_message, level="error")
        )
        if self.pending_refresh_notice:
            self.pending_refresh_notice = False

    def on_champions_loaded(self, data) -> None:
        """英雄数据加载完成。"""
        logger.info(f"champions 实体列表已刷新，当前展示 {len(data)} 项")
        self.entity_data_replaced.emit(EntityRowsPayload.from_rows("champions", data))

        if self.data_app_context is None:
            logger.error("AppContext 未初始化，无法继续加载 maps 数据")
            self.finish_data_loading()
            return

        self.loading_state_changed.emit(
            SharedDataLoadingState(message="正在扫描地图数据…", active=True)
        )
        logger.debug("准备启动 maps 实体状态扫描线程")
        self._maps_worker = self._data_load_worker_cls(self.data_app_context, "maps")
        self._maps_worker.finished.connect(self.on_maps_loaded)
        self._maps_worker.error.connect(self.on_data_load_error)
        self._maps_worker.start()

    def on_maps_loaded(self, data) -> None:
        """地图数据加载完成。"""
        logger.info(f"maps 实体列表已刷新，当前展示 {len(data)} 项")
        self.entity_data_replaced.emit(EntityRowsPayload.from_rows("maps", data))
        self.finish_data_loading()

    def on_data_load_error(self, error) -> None:
        """共享实体数据扫描失败。"""
        self.is_loading_shared_data = False
        if (
            self.allow_auto_prepare_on_shared_reload
            and not self.shared_data_auto_prepare_attempted
            and self.should_auto_prepare_shared_data(str(error))
        ):
            self.shared_data_auto_prepare_attempted = True
            logger.info("共享数据缺失或版本不兼容，转入后台数据准备流程")
            self.loading_state_changed.emit(
                SharedDataLoadingState(message="正在刷新基础数据…", active=True)
            )
            self.start_shared_data_prepare(self._get_config())
            return
        self.loading_state_changed.emit(
            SharedDataLoadingState(message=f"加载失败: {error}", active=False)
        )
        if self.pending_refresh_notice:
            self.notice_requested.emit(
                GuiNotice(title="刷新失败", content=str(error), level="error")
            )
            self.pending_refresh_notice = False
        self.flush_pending_runtime_entity_refresh()

    def finish_data_loading(self) -> None:
        """完成共享数据加载。"""
        self.is_loading_shared_data = False
        self.loading_state_changed.emit(
            SharedDataLoadingState(message="实体数据已就绪", active=False)
        )
        if self.pending_refresh_notice:
            self.notice_requested.emit(
                GuiNotice(
                    title="数据已刷新",
                    content="列表内容已经更新，可以继续查看或创建任务。",
                    level="success",
                )
            )
            self.pending_refresh_notice = False
        self.flush_pending_runtime_entity_refresh()

    def refresh_shared_output_state(self, refresh_request: object | None = None) -> None:
        """仅刷新解包产物对应的实体检测状态与输出扫描结果。"""
        current_cfg = self._get_config()
        self.reconfigure_runtime_logging_requested.emit(
            RuntimeLoggingConfig.from_gui_config(current_cfg)
        )
        if self._has_incomplete_tasks():
            logger.debug("执行中心仍有未完成任务，忽略共享刷新请求")
            self.notice_requested.emit(
                GuiNotice(
                    title="队列未清空",
                    content="请等待当前任务队列全部结束后再刷新列表数据。",
                    level="warning",
                )
            )
            return
        if self.is_loading_shared_data or self.is_preparing_shared_data:
            logger.debug("共享数据仍在加载中，忽略重复刷新请求")
            return

        request = refresh_request if isinstance(refresh_request, OutputStateRefreshRequest) else None
        self.pending_refresh_notice = True
        if self.data_app_context is None:
            logger.info("共享上下文尚未就绪，回退到完整共享数据刷新")
            self.request_shared_data_reload(show_notice=True, allow_auto_prepare=True)
            return

        if request is not None and not request.requires_full_refresh and request.has_incremental_targets():
            logger.info("开始增量刷新共享输出状态")
            try:
                loader = self._entity_data_loader_cls(self.data_app_context)
                if request.champion_ids:
                    champion_rows = loader.load_entities_by_ids("champions", request.champion_ids)
                    self.entity_rows_updated.emit(
                        EntityRowsPayload.from_rows("champions", champion_rows)
                    )
                if request.map_ids:
                    map_rows = loader.load_entities_by_ids("maps", request.map_ids)
                    self.entity_rows_updated.emit(
                        EntityRowsPayload.from_rows("maps", map_rows)
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"增量刷新共享输出状态失败，回退到全量刷新: {exc}")
                self.request_shared_data_reload(show_notice=True, allow_auto_prepare=True)
                return

            if self.pending_refresh_notice:
                self.notice_requested.emit(
                    GuiNotice(
                        title="数据已刷新",
                        content="列表内容已经更新，可以继续查看或创建任务。",
                        level="success",
                    )
                )
                self.pending_refresh_notice = False
            return

        logger.info("开始刷新共享输出状态")
        self.allow_auto_prepare_on_shared_reload = False
        self.shared_data_auto_prepare_attempted = False
        self.is_loading_shared_data = True
        self.loading_state_changed.emit(
            SharedDataLoadingState(message="正在刷新输出状态…", active=True)
        )
        self._champions_worker = self._data_load_worker_cls(self.data_app_context, "champions")
        self._champions_worker.finished.connect(self.on_champions_loaded)
        self._champions_worker.error.connect(self.on_data_load_error)
        self._champions_worker.start()

    def reload_unpack_data(self, cfg=None) -> None:
        """重新加载页面共用的实体数据。"""
        current_cfg = cfg or self._get_config()
        block_reason = self._get_app_context_block_reason(current_cfg)
        if block_reason is not None:
            logger.info(f"共享实体数据重载已跳过: {block_reason}")
            self._apply_blocked_state(block_reason)
            return

        self.data_app_context = None
        self.shared_data_cleared.emit()
        self.app_context_changed.emit(None)
        self.loading_state_changed.emit(
            SharedDataLoadingState(message="正在重新加载数据…", active=True)
        )
        self.load_initial_data(current_cfg)

    def on_shared_context_input_changed(self, cfg=None) -> None:
        """根据共享上下文输入变化类型安排共享实体数据刷新。"""
        current_cfg = cfg or self._get_config()
        current_reader_signature = build_shared_entity_reader_signature(current_cfg)
        current_scan_signature = build_shared_entity_scan_signature(current_cfg)
        reader_changed = current_reader_signature != self.shared_entity_reader_signature
        scan_changed = current_scan_signature != self.shared_entity_scan_signature

        if scan_changed:
            self.reconfigure_runtime_logging_requested.emit(
                RuntimeLoggingConfig.from_gui_config(current_cfg)
            )

        self.shared_entity_reader_signature = current_reader_signature
        self.shared_entity_scan_signature = current_scan_signature

        if not reader_changed and not scan_changed:
            return

        self.pending_runtime_entity_refresh = True
        self.pending_runtime_entity_refresh_allow_auto_prepare = (
            self.pending_runtime_entity_refresh_allow_auto_prepare or reader_changed
        )
        self.pending_runtime_entity_refresh_reset_reader = (
            self.pending_runtime_entity_refresh_reset_reader or reader_changed
        )
        self.schedule_runtime_entity_refresh()

    def schedule_runtime_entity_refresh(self) -> None:
        """为运行时配置变更安排一次共享实体数据刷新。"""
        if self._has_incomplete_tasks():
            logger.debug("任务队列未清空，延后处理运行时配置对应的实体数据刷新")
            return
        if self.is_loading_shared_data or self.is_preparing_shared_data:
            logger.debug("共享数据刷新仍在进行中，保留待处理的运行时配置刷新")
            return
        self.runtime_entity_refresh_timer.start()

    def flush_pending_runtime_entity_refresh(self) -> None:
        """在合适时机执行待处理的运行时配置刷新。"""
        if not self.pending_runtime_entity_refresh:
            return
        if self._has_incomplete_tasks():
            return
        if self.is_loading_shared_data or self.is_preparing_shared_data:
            return
        allow_auto_prepare = self.pending_runtime_entity_refresh_allow_auto_prepare
        reset_reader = self.pending_runtime_entity_refresh_reset_reader
        self.pending_runtime_entity_refresh = False
        self.pending_runtime_entity_refresh_allow_auto_prepare = False
        self.pending_runtime_entity_refresh_reset_reader = False
        if reset_reader:
            self._reset_data_reader_singleton()
        self.request_shared_data_reload(show_notice=False, allow_auto_prepare=allow_auto_prepare)

    def request_shared_data_reload(self, *, show_notice: bool, allow_auto_prepare: bool) -> None:
        """启动一次共享实体数据刷新流程。"""
        self.pending_refresh_notice = show_notice
        self.allow_auto_prepare_on_shared_reload = allow_auto_prepare
        self.shared_data_auto_prepare_attempted = False
        self.reload_unpack_data(self._get_config())

    def should_auto_prepare_shared_data(self, error: str) -> bool:
        """判断当前共享数据加载错误是否适合自动补一次后端更新。"""
        normalized = str(error)
        return (
            "请先运行更新程序" in normalized
            or "请立即运行数据更新程序" in normalized
            or "核心数据文件" in normalized
            or "数据版本与游戏版本严重不匹配" in normalized
        )

    def start_shared_data_prepare(self, cfg=None) -> None:
        """在后台线程中补齐共享实体数据所需的后端更新。"""
        current_cfg = cfg or self._get_config()
        if self.shared_data_prepare_worker is not None:
            return

        overrides = dict(current_cfg.to_app_context_overrides())

        def run_prepare() -> None:
            self._prepare_shared_entity_data(overrides)

        worker = self._task_worker_cls(run_prepare)
        worker.signals.started.connect(self.on_shared_data_prepare_started)
        worker.signals.finished.connect(
            lambda _result, refresh_cfg=current_cfg: self.on_shared_data_prepare_finished(refresh_cfg)
        )
        worker.signals.failed.connect(self.on_shared_data_prepare_failed)
        self.shared_data_prepare_worker = worker
        self._start_worker(worker)

    def on_shared_data_prepare_started(self) -> None:
        """同步后台共享数据准备开始时的界面状态。"""
        self.is_preparing_shared_data = True
        self.loading_state_changed.emit(
            SharedDataLoadingState(message="正在刷新基础数据…", active=True)
        )

    def on_shared_data_prepare_finished(self, cfg) -> None:
        """在后台数据准备结束后重新加载共享实体数据。"""
        self.is_preparing_shared_data = False
        self.shared_data_prepare_worker = None
        self.reload_unpack_data(cfg)

    def on_shared_data_prepare_failed(self, error: str) -> None:
        """处理后台共享数据准备失败后的界面状态。"""
        self.is_preparing_shared_data = False
        self.shared_data_prepare_worker = None
        self.loading_state_changed.emit(
            SharedDataLoadingState(message=f"加载失败: {error}", active=False)
        )
        if self.pending_refresh_notice:
            self.notice_requested.emit(
                GuiNotice(title="刷新失败", content=error, level="error")
            )
            self.pending_refresh_notice = False

    def _apply_blocked_state(self, message: str) -> None:
        """在共享数据暂不可用时切到空状态而不是错误态。"""
        self.is_loading_shared_data = False
        self.shared_context_build_timeout_timer.stop()
        self.shared_context_build_worker = None
        self.shared_context_build_cfg = None
        self.data_app_context = None
        self.shared_data_cleared.emit()
        self.app_context_changed.emit(None)
        self.loading_state_changed.emit(
            SharedDataLoadingState(message=message, active=False)
        )
        if self.pending_refresh_notice:
            self.pending_refresh_notice = False
