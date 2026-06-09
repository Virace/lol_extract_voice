"""验证 AppContext 暴露 mapping 所需的稳定派生值。"""

from pathlib import Path

import pytest

from lol_audio_unpack.app.types import AppConfig, AppContext, AppPaths

pytestmark = pytest.mark.unit

FAKE_GAME_PATH = Path("FakeGame")
FAKE_OUTPUT_PATH = Path("FakeOut")


def _build_ctx() -> AppContext:
    game_path = FAKE_GAME_PATH
    output_path = FAKE_OUTPUT_PATH
    return AppContext(
        config=AppConfig(
            game_path=game_path,
            output_path=output_path,
            game_region="en_US",
        ),
        paths=AppPaths(
            audio_path=output_path / "audios",
            wav_path=output_path / "wavs",
            temp_path=output_path / "temps",
            log_path=output_path / "logs",
            cache_path=output_path / "cache",
            hash_path=output_path / "hashes",
            report_path=output_path / "reports",
            manifest_path=output_path / "manifest",
            local_version_file=output_path / "game_version",
            game_champion_path=game_path / "Game" / "DATA" / "FINAL" / "Champions",
            game_maps_path=game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
            game_lcu_path=game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        ),
    )


def test_app_context_exposes_mapping_runtime_paths() -> None:
    """mapping 侧应通过 AppContext 读取标准化后的派生路径。"""
    ctx = _build_ctx()

    assert ctx.game_path == FAKE_GAME_PATH
    assert ctx.cache_path == FAKE_OUTPUT_PATH / "cache"
    assert ctx.hash_path == FAKE_OUTPUT_PATH / "hashes"
