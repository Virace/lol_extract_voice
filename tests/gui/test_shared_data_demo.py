"""共享数据进度 mock 测试。"""

from __future__ import annotations

from lol_audio_unpack.gui.controllers.shared_data_demo import build_shared_data_demo_states
from lol_audio_unpack.gui.shared_data import SharedDataPhase
from lol_audio_unpack.gui.shared_data_view import describe_shared_data_state
from lol_audio_unpack.model.progress import OperationProgress

TEST_CHAMPION_TOTAL = 3
TEST_MAP_TOTAL = 2
TEST_CHAMPION_CURRENT = 2


def test_shared_data_demo_covers_complete_progress_flow() -> None:
    states = build_shared_data_demo_states(
        generation=7,
        source_mode="local_path",
        champion_total=TEST_CHAMPION_TOTAL,
        map_total=TEST_MAP_TOTAL,
    )

    phases = [state.phase for state in states]
    champion_update = next(
        state
        for state in states
        if isinstance(state.progress, OperationProgress)
        and state.progress.stage_key == "champion_banks"
        and state.progress.current == TEST_CHAMPION_CURRENT
    )
    champion_display = describe_shared_data_state(champion_update)

    assert phases[0] is SharedDataPhase.CHECKING
    assert SharedDataPhase.PREPARING in phases
    assert SharedDataPhase.VERIFYING in phases
    assert phases[-1] is SharedDataPhase.READY
    assert champion_display.progress_text == f"英雄数据 · {TEST_CHAMPION_CURRENT}/{TEST_CHAMPION_TOTAL}"
    assert (champion_display.progress_current, champion_display.progress_total) == (
        TEST_CHAMPION_CURRENT,
        TEST_CHAMPION_TOTAL,
    )
    assert states[-1].summary is not None
    assert states[-1].summary.champion_loaded == TEST_CHAMPION_TOTAL
    assert states[-1].summary.map_loaded == TEST_MAP_TOTAL


def test_shared_data_demo_emits_normalized_stage_boundaries() -> None:
    states = build_shared_data_demo_states(
        generation=2,
        source_mode="remote_snapshot",
        champion_total=2,
        map_total=1,
    )

    progress = [state.progress for state in states if state.progress is not None]

    assert all(item.current is not None and 0 <= item.current <= item.total for item in progress)
    assert {item.event for item in progress} == {"started", "advanced", "finished"}
