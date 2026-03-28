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
