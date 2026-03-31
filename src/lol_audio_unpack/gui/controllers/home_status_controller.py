"""首页状态检查控制器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal

from lol_audio_unpack.gui.workers import TaskWorker
from lol_audio_unpack.manager.utils import get_game_version


@dataclass(frozen=True, slots=True)
class HomeCheckResult:
    """后台首页检查结果。"""

    version: str
    version_error: str
    cache_found: bool
    cache_path: str


@dataclass(frozen=True, slots=True)
class HomeStatusDisplayState:
    """首页卡片可直接消费的显示状态。"""

    current_version: str
    version_text: str
    version_jump_enabled: bool
    cache_text: str
    cache_path: str
    cache_jump_enabled: bool


def check_audio_cache(output_path: Path, major_minor: str) -> tuple[bool, str]:
    """检查 ``audios/<major.minor>*`` 是否存在。"""
    audios_dir = output_path / "audios"
    if not audios_dir.is_dir():
        return False, ""
    for child in audios_dir.iterdir():
        if child.is_dir() and child.name.startswith(major_minor):
            return True, str(child)
    return False, ""


class HomeStatusController(QObject):
    """负责首页版本/缓存状态的后台检查与显示态转换。"""

    display_state_ready = Signal(object)

    def __init__(
        self,
        *,
        get_game_version_fn: Callable[[Path], str] = get_game_version,
        cache_check_fn: Callable[[Path, str], tuple[bool, str]] = check_audio_cache,
        task_worker_cls=TaskWorker,
        start_worker_fn: Callable[[object], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """初始化首页状态控制器。

        Args:
            get_game_version_fn: 获取游戏版本的函数。
            cache_check_fn: 检查缓存目录的函数。
            task_worker_cls: 后台 worker 类型。
            start_worker_fn: 启动 worker 的函数。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._get_game_version = get_game_version_fn
        self._cache_check = cache_check_fn
        self._task_worker_cls = task_worker_cls
        self._start_worker = start_worker_fn or QThreadPool.globalInstance().start
        self._active_worker = None

    def has_active_background_check(self) -> bool:
        """返回首页状态后台检查是否仍在运行。"""
        return self._active_worker is not None

    def run_check(self, *, game_path: Path | None, output_path: Path) -> HomeCheckResult:
        """执行一次首页状态检查。

        Args:
            game_path: 当前游戏根目录。
            output_path: 当前输出目录。

        Returns:
            HomeCheckResult: 后台检查结果。
        """
        if game_path is None:
            return HomeCheckResult(
                version="",
                version_error="游戏目录未设置",
                cache_found=False,
                cache_path="",
            )
        try:
            version = self._get_game_version(game_path)
        except Exception as exc:  # noqa: BLE001
            return HomeCheckResult(
                version="",
                version_error=str(exc),
                cache_found=False,
                cache_path="",
            )

        found, matched = self._cache_check(output_path, version)
        return HomeCheckResult(
            version=version,
            version_error="",
            cache_found=found,
            cache_path=matched,
        )

    def build_display_state(
        self,
        *,
        result: HomeCheckResult,
        output_path: Path,
    ) -> HomeStatusDisplayState:
        """把后台检查结果转换为首页卡片展示状态。"""
        if result.version_error:
            return HomeStatusDisplayState(
                current_version="",
                version_text=result.version_error,
                version_jump_enabled=False,
                cache_text="无法获取版本",
                cache_path="",
                cache_jump_enabled=False,
            )

        if result.cache_found:
            return HomeStatusDisplayState(
                current_version=result.version,
                version_text=result.version,
                version_jump_enabled=False,
                cache_text=f"已找到 {result.version}",
                cache_path=result.cache_path,
                cache_jump_enabled=True,
            )

        return HomeStatusDisplayState(
            current_version=result.version,
            version_text=result.version,
            version_jump_enabled=False,
            cache_text=f"无 {result.version} 缓存",
            cache_path=str(output_path / "audios"),
            cache_jump_enabled=True,
        )

    def build_failure_state(self) -> HomeStatusDisplayState:
        """构造后台异常时的兜底显示状态。"""
        return HomeStatusDisplayState(
            current_version="",
            version_text="读取失败",
            version_jump_enabled=False,
            cache_text="检查失败",
            cache_path="",
            cache_jump_enabled=False,
        )

    def start_check(self, *, game_path: Path | None, output_path: Path) -> None:
        """启动一次后台首页状态检查。"""

        def _check() -> HomeCheckResult:
            return self.run_check(game_path=game_path, output_path=output_path)

        worker = self._task_worker_cls(_check)
        worker.signals.finished.connect(
            lambda result, output_path=output_path: self._emit_finished_state(
                result=result,
                output_path=output_path,
            )
        )
        worker.signals.failed.connect(
            lambda _error: self._emit_failure_state()
        )
        self._active_worker = worker
        self._start_worker(worker)

    def _emit_finished_state(self, *, result: HomeCheckResult, output_path: Path) -> None:
        """广播首页状态检查成功结果，并释放当前 worker 引用。"""
        self._active_worker = None
        self.display_state_ready.emit(
            self.build_display_state(result=result, output_path=output_path)
        )

    def _emit_failure_state(self) -> None:
        """广播首页状态检查失败结果，并释放当前 worker 引用。"""
        self._active_worker = None
        self.display_state_ready.emit(self.build_failure_state())

    def shutdown(self) -> None:
        """清理首页状态检查的运行期引用。"""
        self._active_worker = None
