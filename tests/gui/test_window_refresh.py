"""测试主窗口中的共享输出刷新策略。"""

from __future__ import annotations

from types import SimpleNamespace

import lol_audio_unpack.gui.window as window_module
from lol_audio_unpack.gui.task_models import OutputStateRefreshRequest
from lol_audio_unpack.gui.window import MainWindow


class _FakeEmitter:
    """记录信号连接目标的轻量替身。"""

    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def connect(self, callback: object) -> None:
        """记录一次 connect 调用。"""
        self.callbacks.append(callback)


def _build_shared_cfg(*, source_mode: str = "local_path", game_path: str = "", output_path: str = ""):
    """构造共享实体数据相关的最小配置替身。"""

    class _Cfg:
        page_smooth_scroll_enabled = False
        widget_smooth_scroll_enabled = False
        log_drawer_auto_collapse_enabled = True

        def __init__(self) -> None:
            self.source_mode = source_mode
            self.game_path = game_path
            self.output_path = output_path

        def resolve_game_path(self):
            return None if not self.game_path else object()

        def to_app_context_overrides(self) -> dict[str, str | bool]:
            return {
                "SOURCE_MODE": self.source_mode,
                "GAME_PATH": self.game_path,
                "OUTPUT_PATH": self.output_path,
                "GAME_REGION": "zh_CN",
                "GROUP_BY_TYPE": False,
                "REMOTE_LIVE_REGION": "EUW",
                "CLEANUP_REMOTE": True,
                "REMOTE_VERSION": "",
                "REMOTE_LCU_MANIFEST_URL": "",
                "REMOTE_GAME_MANIFEST_URL": "",
                "WWISER_PATH": "",
            }

    return _Cfg()


def test_window_connect_pages_skips_initial_shared_load_without_game_path(monkeypatch) -> None:
    """首次启动缺少游戏目录时不应触发首轮共享数据加载。"""
    calls: list[tuple[object, ...]] = []
    cfg = _build_shared_cfg(output_path="")

    fake_window = SimpleNamespace(
        settingInterface=SimpleNamespace(
            config=cfg,
            game_path_changed=_FakeEmitter(),
            output_path_changed=_FakeEmitter(),
            wwiser_path_changed=_FakeEmitter(),
            vgmstream_path_changed=_FakeEmitter(),
            shared_context_input_changed=_FakeEmitter(),
            smooth_scroll_changed=_FakeEmitter(),
            log_drawer_auto_collapse_changed=_FakeEmitter(),
            log_levels_changed=_FakeEmitter(),
        ),
        homeInterface=SimpleNamespace(
            update_game_dir=lambda path: calls.append(("update_game_dir", path)),
            update_output_dir=lambda path: calls.append(("update_output_dir", path)),
            update_wwiser=lambda path: calls.append(("update_wwiser", path)),
            update_vgmstream=lambda path: calls.append(("update_vgmstream", path)),
            navigate_to_execution_requested=_FakeEmitter(),
            set_loading_state=lambda text, active: calls.append(("loading_state", text, active)),
        ),
        executionInterface=SimpleNamespace(
            set_gui_config=lambda current_cfg: calls.append(("execution_set_gui_config", current_cfg)),
            output_state_refresh_requested=_FakeEmitter(),
            task_queue_busy_changed=_FakeEmitter(),
            log_lines_appended=_FakeEmitter(),
            clear_entity_data=lambda: calls.append(("clear_entity_data",)),
        ),
        overviewInterface=SimpleNamespace(
            set_gui_config=lambda current_cfg: calls.append(("overview_set_gui_config", current_cfg)),
            selection_sync_requested=_FakeEmitter(),
            set_app_context=lambda app_context: calls.append(("set_app_context", app_context)),
            clear_data=lambda: calls.append(("clear_data",)),
        ),
        _sync_selection_to_execution_center=lambda *args: calls.append(("sync_selection", args)),
        _refresh_shared_output_state=lambda *args: calls.append(("refresh_output", args)),
        _on_task_queue_busy_changed=lambda *args: calls.append(("queue_busy", args)),
        _append_global_log_lines=lambda *args: calls.append(("append_log_lines", args)),
        _on_shared_context_input_changed=lambda *args: calls.append(("shared_context_changed", args)),
        _apply_smooth_scroll_setting=lambda *args: calls.append(("smooth_scroll", args)),
        _apply_log_drawer_auto_collapse_setting=lambda *args: calls.append(("log_drawer", args)),
        _reconfigure_runtime_logging=lambda *args: calls.append(("reconfigure_logging", args)),
        switchTo=lambda *args: calls.append(("switch_to", args)),
        _load_initial_data=lambda current_cfg: calls.append(("load_initial_data", current_cfg)),
        _shared_entity_reader_signature=None,
        _shared_entity_scan_signature=None,
    )

    MainWindow._connect_pages(fake_window)

    assert not any(entry[0] == "load_initial_data" for entry in calls)
    assert ("clear_entity_data",) in calls
    assert ("clear_data",) in calls
    assert ("set_app_context", None) in calls
    assert ("loading_state", "请先在「全局设置」中配置游戏目录。", False) in calls


def test_window_reload_unpack_data_skips_reload_when_game_path_missing(monkeypatch) -> None:
    """共享配置未完成时不应进入重新加载流程。"""
    calls: list[tuple[object, ...]] = []
    cfg = _build_shared_cfg(output_path="")

    fake_window = SimpleNamespace(
        _data_app_context={"runtime": "shared"},
        executionInterface=SimpleNamespace(clear_entity_data=lambda: calls.append(("clear_entity_data",))),
        overviewInterface=SimpleNamespace(
            clear_data=lambda: calls.append(("clear_data",)),
            set_app_context=lambda app_context: calls.append(("set_app_context", app_context)),
        ),
        homeInterface=SimpleNamespace(
            set_loading_state=lambda text, active: calls.append(("loading_state", text, active)),
        ),
        _load_initial_data=lambda current_cfg: calls.append(("load_initial_data", current_cfg)),
    )

    MainWindow._reload_unpack_data(fake_window, cfg)

    assert fake_window._data_app_context is None
    assert ("clear_entity_data",) in calls
    assert ("clear_data",) in calls
    assert ("set_app_context", None) in calls
    assert ("loading_state", "请先在「全局设置」中配置游戏目录。", False) in calls
    assert not any(entry[0] == "load_initial_data" for entry in calls)


def test_window_refresh_shared_output_state_reuses_existing_context(monkeypatch) -> None:
    """任务完成后的输出状态刷新不应默认重建共享 reader。"""
    calls: list[tuple[object, ...]] = []

    class FakeDataLoadWorker:
        """替代线程 worker，记录是否基于现有上下文启动扫描。"""

        def __init__(self, app_context, entity_type: str) -> None:
            self.app_context = app_context
            self.entity_type = entity_type
            self.finished = _FakeEmitter()
            self.error = _FakeEmitter()
            calls.append(("worker_init", app_context, entity_type))

        def start(self) -> None:
            """记录线程启动。"""
            calls.append(("worker_start", self.entity_type))

    monkeypatch.setattr(window_module, "DataLoadWorker", FakeDataLoadWorker)
    monkeypatch.setattr(window_module, "_reset_data_reader_singleton", lambda: calls.append(("reset_reader",)))

    fake_window = SimpleNamespace(
        settingInterface=SimpleNamespace(config=object()),
        executionInterface=SimpleNamespace(has_incomplete_tasks=lambda: False),
        homeInterface=SimpleNamespace(
            set_loading_state=lambda text, active: calls.append(("loading_state", text, active)),
        ),
        _data_app_context={"runtime": "shared"},
        _is_loading_shared_data=False,
        _is_preparing_shared_data=False,
        _pending_refresh_notice=False,
        _allow_auto_prepare_on_shared_reload=True,
        _shared_data_auto_prepare_attempted=False,
        _champions_worker=None,
        _maps_worker=None,
        _on_champions_loaded=object(),
        _on_maps_loaded=object(),
        _on_data_load_error=object(),
        _reconfigure_runtime_logging=lambda cfg: calls.append(("reconfigure_logging", cfg)),
        _request_shared_data_reload=lambda **kwargs: calls.append(("full_reload", kwargs)),
    )

    MainWindow._refresh_shared_output_state(fake_window)

    assert ("reset_reader",) not in calls
    assert not any(entry[0] == "full_reload" for entry in calls)
    assert ("worker_init", {"runtime": "shared"}, "champions") in calls
    assert ("worker_start", "champions") in calls


def test_window_refresh_shared_output_state_can_update_incrementally(monkeypatch) -> None:
    """定向任务完成后应只刷新受影响实体，而不是回退全量扫描。"""
    calls: list[tuple[object, ...]] = []

    class FakeLoader:
        def __init__(self, app_context) -> None:
            calls.append(("loader_init", app_context))

        def load_entities_by_ids(self, entity_type: str, entity_ids: tuple[str, ...]) -> list[dict[str, str]]:
            calls.append(("load_entities_by_ids", entity_type, entity_ids))
            return [
                {
                    "id": entity_ids[0],
                    "name": "Annie",
                    "alias": "annie",
                    "audio": "已存在",
                    "mapping": "已存在",
                    "entity_type": entity_type,
                    "mapping_file": "",
                }
            ]

    monkeypatch.setattr(window_module, "EntityDataLoader", FakeLoader)

    fake_window = SimpleNamespace(
        settingInterface=SimpleNamespace(config=object()),
        executionInterface=SimpleNamespace(
            has_incomplete_tasks=lambda: False,
            update_entity_rows=lambda entity_type, rows: calls.append(("execution_update", entity_type, rows)),
        ),
        overviewInterface=SimpleNamespace(
            update_entity_rows=lambda entity_type, rows: calls.append(("overview_update", entity_type, rows)),
        ),
        homeInterface=SimpleNamespace(
            set_loading_state=lambda text, active: calls.append(("loading_state", text, active)),
        ),
        _data_app_context={"runtime": "shared"},
        _is_loading_shared_data=False,
        _is_preparing_shared_data=False,
        _pending_refresh_notice=False,
        _allow_auto_prepare_on_shared_reload=True,
        _shared_data_auto_prepare_attempted=False,
        _reconfigure_runtime_logging=lambda cfg: calls.append(("reconfigure_logging", cfg)),
        _request_shared_data_reload=lambda **kwargs: calls.append(("full_reload", kwargs)),
        _show_refresh_infobar=lambda **kwargs: calls.append(("infobar", kwargs)),
    )

    MainWindow._refresh_shared_output_state(
        fake_window,
        OutputStateRefreshRequest(champion_ids=("1",)),
    )

    assert ("loader_init", {"runtime": "shared"}) in calls
    assert ("load_entities_by_ids", "champions", ("1",)) in calls
    assert any(entry[0] == "execution_update" for entry in calls)
    assert any(entry[0] == "overview_update" for entry in calls)
    assert not any(entry[0] == "full_reload" for entry in calls)
    assert (
        "infobar",
        {
            "title": "数据已刷新",
            "content": "列表内容已经更新，可以继续查看或创建任务。",
            "level": "success",
        },
    ) in calls
