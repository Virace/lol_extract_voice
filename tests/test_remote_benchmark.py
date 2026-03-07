import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from riotmanifest import VersionMatchMode

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_remote_live.py"
SPEC = importlib.util.spec_from_file_location("benchmark_remote_live", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

pytestmark = pytest.mark.unit


def test_parse_id_csv_returns_int_tuple() -> None:
    assert MODULE.parse_id_csv("1, 103,555") == (1, 103, 555)


def test_build_config_requires_exactly_three_champions(tmp_path: Path) -> None:
    args = SimpleNamespace(
        report=Path("benchmarks/remote_live/latest.json"),
        output_root=Path(".cache/remote_live_benchmark"),
        live_region="EUW",
        game_region="zh_CN",
        champion_ids="1,2",
        map_id=11,
        max_workers=1,
        sampling_interval=0.5,
        cleanup_remote=True,
        integrate_data=True,
        auto_download_wwiser=True,
        wwiser_path=None,
    )

    with pytest.raises(ValueError):
        MODULE.build_config(args, tmp_path)


def test_validate_extract_artifacts_counts_champion_outputs(tmp_path: Path) -> None:
    version = "16.5"
    audio_root = tmp_path / "audios" / version / "champions" / "1·annie" / "1000·基础皮肤" / "VO"
    audio_root.mkdir(parents=True, exist_ok=True)
    (audio_root / "123.wem").write_bytes(b"abc")
    report_file = tmp_path / "reports" / version / "champions" / "_1_metadata.yaml"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text("ok\n", encoding="utf-8")

    artifacts, errors = MODULE._validate_extract_artifacts(
        output_path=tmp_path,
        version=version,
        entity_type="champion",
        ids=(1,),
    )

    assert artifacts["wem_count_by_id"]["1"] == 1
    assert artifacts["report_exists_by_id"]["1"] is True
    assert errors == []


def test_validate_mapping_artifacts_checks_integrated_files(tmp_path: Path) -> None:
    version = "16.5"
    mapping_file = tmp_path / "hashes" / version / "maps" / "11.msgpack"
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    mapping_file.write_bytes(b"mapping")
    integrated_file = tmp_path / "hashes" / version / "integrated" / "maps" / "11.msgpack"
    integrated_file.parent.mkdir(parents=True, exist_ok=True)
    integrated_file.write_bytes(b"integrated")

    artifacts, errors = MODULE._validate_mapping_artifacts(
        output_path=tmp_path,
        version=version,
        entity_type="map",
        ids=(11,),
        integrate_data=True,
    )

    assert artifacts["mapping_files"]["11"].endswith("11.msgpack")
    assert artifacts["integrated_files"]["11"].endswith("11.msgpack")
    assert errors == []


def test_validate_mapping_artifacts_allows_missing_mapping_file_when_integrated_enabled(tmp_path: Path) -> None:
    version = "16.5"
    integrated_file = tmp_path / "hashes" / version / "integrated" / "maps" / "11.msgpack"
    integrated_file.parent.mkdir(parents=True, exist_ok=True)
    integrated_file.write_bytes(b"integrated")

    artifacts, errors = MODULE._validate_mapping_artifacts(
        output_path=tmp_path,
        version=version,
        entity_type="map",
        ids=(11,),
        integrate_data=True,
    )

    assert artifacts["mapping_files"]["11"] == ""
    assert artifacts["integrated_files"]["11"].endswith("11.msgpack")
    assert errors == []


def test_build_markdown_summary_includes_stage_table() -> None:
    payload = {
        "meta": {
            "generated_at": "2026-03-07T15:00:00+08:00",
            "live_region": "EUW",
            "game_region": "zh_CN",
            "version": "16.5",
            "match_mode": "ignore_revision",
            "champion_ids": [1, 103, 555],
            "map_id": 11,
            "integrate_data": True,
            "cleanup_remote": True,
            "wwiser_path": "/tmp/wwiser.pyz",
        },
        "scenarios": [
            {
                "scenario": "champions_full_chain",
                "output_path": "/tmp/out",
                "summary": {
                    "status": "ok",
                    "total_duration_seconds": 12.3,
                    "overall_peak_human": "1.00GiB",
                    "final_human": "2.00MiB",
                },
                "stages": [
                    {
                        "stage": "update",
                        "status": "ok",
                        "duration_seconds": 1.2,
                        "peak_human": "1.00GiB",
                        "post_stage_human": "900.00MiB",
                        "post_cleanup_human": "5.00MiB",
                        "error": "",
                    }
                ],
            }
        ],
    }

    markdown = MODULE.build_markdown_summary(payload)

    assert "Remote Live Benchmark 报告" in markdown
    assert "| 阶段 | 状态 | 用时(s) | 峰值占用 | 阶段结束占用 | 清理后占用 |" in markdown
    assert "champions_full_chain" in markdown
    assert "版本匹配模式" in markdown


def test_resolve_snapshot_meta_uses_ignore_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePair:
        version = "16.5"
        lcu = SimpleNamespace(url="https://example.com/lcu.manifest")
        game = SimpleNamespace(url="https://example.com/game.manifest")

    class FakeRiotGameData:
        def resolve_live_manifest_pair(self, region: str, *, match_mode: VersionMatchMode):
            assert region == "EUW"
            assert match_mode is VersionMatchMode.IGNORE_REVISION
            return FakePair()

    monkeypatch.setattr(MODULE, "RiotGameData", FakeRiotGameData)

    meta = MODULE._resolve_snapshot_meta("EUW", match_mode=VersionMatchMode.IGNORE_REVISION)

    assert meta.version == "16.5"
