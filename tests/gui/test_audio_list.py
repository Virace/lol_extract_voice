"""验证全部音频平铺列表的路径级模型行为。"""

from __future__ import annotations

from pathlib import Path

from lol_audio_unpack.app.artifacts import AudioRef
from lol_audio_unpack.gui.components.audio_list import AUDIO_REF_ROLE, AudioListView

EXPECTED_DUPLICATE_REF_COUNT = 2
EXPECTED_PLAYBACK_PROGRESS = 0.42


def _make_ref(relative_path: str, *, audio_type: str | None = "VO") -> AudioRef:
    """构造路径级列表测试所需的最小 WEM 引用。"""
    return AudioRef(
        relative_path=relative_path,
        path=Path("audios") / relative_path,
        wem_id=Path(relative_path).stem,
        audio_type=audio_type,
        sub_entity="1000",
    )


def test_audio_list_keeps_duplicate_wem_ids_as_distinct_path_items(qtbot) -> None:
    view = AudioListView()
    qtbot.addWidget(view)
    first = _make_ref("1000/VO/1001.wem")
    second = _make_ref("1001/VO/1001.wem")

    view.set_audio_refs((first, second))

    model = view.model()
    assert model.rowCount() == EXPECTED_DUPLICATE_REF_COUNT
    assert model.data(model.index(0, 0), AUDIO_REF_ROLE) == first
    assert model.data(model.index(1, 0), AUDIO_REF_ROLE) == second


def test_audio_list_filter_matches_relative_path_and_reliable_audio_type(qtbot) -> None:
    view = AudioListView()
    qtbot.addWidget(view)
    vo_ref = _make_ref("1000/VO/1001.wem")
    sfx_ref = _make_ref("1000/SFX/2001.wem", audio_type="SFX")
    view.set_audio_refs((vo_ref, sfx_ref))

    view.set_keyword("sfx")

    model = view.model()
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0), AUDIO_REF_ROLE) == sfx_ref


def test_audio_list_tracks_playback_by_exact_path(qtbot) -> None:
    view = AudioListView()
    qtbot.addWidget(view)
    first = _make_ref("1000/VO/1001.wem")
    second = _make_ref("1001/VO/1001.wem")
    view.set_audio_refs((first, second))

    view.set_audio_playback_state(
        second.path,
        progress=EXPECTED_PLAYBACK_PROGRESS,
        is_playing=True,
        is_paused=False,
    )

    assert view.is_active(first) is False
    assert view.is_active(second) is True
    assert view.playback_progress(first) == 0.0
    assert view.playback_progress(second) == EXPECTED_PLAYBACK_PROGRESS
    assert view.active_progress == EXPECTED_PLAYBACK_PROGRESS
    assert view.is_playing is True
    assert view.is_paused is False
