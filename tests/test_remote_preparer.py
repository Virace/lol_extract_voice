import io
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

import lol_audio_unpack.facade as m_facade
import lol_audio_unpack.remote_preparer as m_remote
from lol_audio_unpack.app_context import (
    AppConfig,
    AppContext,
    AppPaths,
    OperationOptions,
    RemoteSnapshotConfig,
    SourceMode,
)
from lol_audio_unpack.facade import LolAudioUnpackApp
from lol_audio_unpack.remote_preparer import RemoteSnapshotPreparer

pytestmark = pytest.mark.unit
EXPECTED_BUNDLE_COUNT = 3
EXPECTED_EXTRACTED_BIN_COUNT = 4
EXPECTED_CLEANUP_LCU_WADS = 2


def _build_remote_ctx(tmp_path: Path, *, game_region: str = "zh_CN") -> AppContext:
    output_path = tmp_path / "output"
    game_path = output_path / "_prepared_game"
    app_config = AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=game_region,
        source_mode=SourceMode.REMOTE_SNAPSHOT,
        remote_snapshot=RemoteSnapshotConfig(
            version="16.5",
            lcu_manifest_url="https://example.com/releases/ABCDEF.manifest",
            game_manifest_url="https://example.com/releases/GAME.manifest",
        ),
    )
    app_paths = AppPaths(
        audio_path=output_path / "audios",
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
    )
    return AppContext(config=app_config, paths=app_paths, logger=None, runtime_cache={})


def test_remote_snapshot_preparer_downloads_description_and_required_bundles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    monkeypatch.setattr(m_remote, "urlopen", lambda _url: io.BytesIO(b"manifest-data"))

    class FakeFile:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakePatcherManifest:
        def __init__(self, *, file: Path, path: Path) -> None:
            self.file = file
            self.path = Path(path)
            names = [
                "plugins/rcp-be-lol-game-data/description.json",
                "plugins/rcp-be-lol-game-data/default-assets.wad",
                "plugins/rcp-be-lol-game-data/default-assets2.wad",
                "plugins/rcp-be-lol-game-data/zh_CN-assets.wad",
                "plugins/rcp-be-lol-game-data/fr_FR-assets.wad",
            ]
            self.files = {name: FakeFile(name) for name in names}

        def file_output(self, file: FakeFile) -> str:
            return str(self.path / PurePosixPath(file.name))

        async def download_files_concurrently(self, files, raise_on_error=True):  # noqa: ARG002
            results = []
            for file in files:
                output_path = Path(self.file_output(file))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if file.name.endswith("description.json"):
                    output_path.write_text(
                        json.dumps(
                            {
                                "riotMeta": {
                                    "globalAssetBundles": ["default-assets.wad", "default-assets2.wad"],
                                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                else:
                    output_path.write_bytes(file.name.encode("utf-8"))
                results.append(True)
            return tuple(results)

    monkeypatch.setattr(m_remote, "PatcherManifest", FakePatcherManifest)

    result = RemoteSnapshotPreparer(ctx=ctx).prepare_lcu_game_data()

    assert result.manifest_cache_path.exists()
    assert result.description_cache_path.exists()
    assert len(result.bundle_cache_paths) == EXPECTED_BUNDLE_COUNT
    prepared_root = ctx.paths.game_lcu_path
    assert (prepared_root / "description.json").exists()
    assert (prepared_root / "default-assets.wad").exists()
    assert (prepared_root / "default-assets2.wad").exists()
    assert (prepared_root / "zh_CN-assets.wad").exists()
    assert not (prepared_root / "fr_FR-assets.wad").exists()


def test_ensure_manifest_cached_sends_user_agent_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    captured: dict[str, str] = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["user_agent"] = request.headers.get("User-agent", "")
        return io.BytesIO(b"manifest-data")

    monkeypatch.setattr(m_remote, "urlopen", fake_urlopen)

    preparer = RemoteSnapshotPreparer(ctx=ctx)
    manifest_path = preparer._ensure_manifest_cached(
        manifest_url=ctx.config.remote_snapshot.lcu_manifest_url,
        manifest_cache_dir=preparer.lcu_manifest_cache_dir,
    )

    assert manifest_path.exists()
    assert captured["url"] == ctx.config.remote_snapshot.lcu_manifest_url
    assert captured["user_agent"] == "Mozilla/5.0"


def test_facade_update_prepares_remote_snapshot_before_updaters(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_lcu_game_data(self) -> None:
            call_order.append("prepare_lcu")

        def prepare_bin_inputs(  # noqa: PLR0913
            self,
            *,
            reader,
            target,
            champion_ids=None,
            map_ids=None,
        ) -> None:
            assert reader is not None
            assert target == "all"
            assert champion_ids is None
            assert map_ids is None
            call_order.append("prepare_bin")

    class FakeDataUpdater:
        def __init__(self, force_update=False, ctx=None):  # noqa: ANN001, FBT002
            assert force_update is False
            assert ctx is not None

        def check_and_update(self) -> None:
            call_order.append("data")

    class FakeBinUpdater:
        def __init__(self, force_update=False, process_events=True, ctx=None):  # noqa: ANN001, FBT002
            assert force_update is False
            assert process_events is True
            assert ctx is not None

        def update(self, *, target="all", champion_ids=None, map_ids=None) -> None:  # noqa: ANN001
            assert target == "all"
            assert champion_ids is None
            assert map_ids is None
            call_order.append("bin")

    monkeypatch.setattr(m_facade, "RemoteSnapshotPreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataUpdater", FakeDataUpdater)
    monkeypatch.setattr(m_facade, "BinUpdater", FakeBinUpdater)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx))

    app.update(OperationOptions())

    assert call_order == ["prepare_lcu", "data", "prepare_bin", "bin"]


def test_remote_snapshot_preparer_extracts_bin_inputs_for_bin_updater(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    reader = type(
        "FakeReader",
        (),
        {
            "get_champions": lambda self: [
                {
                    "alias": "Annie",
                    "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
                    "skins": [
                        {"id": 1000, "binPath": "data/characters/Annie/skins/skin0.bin"},
                        {
                            "id": 1001,
                            "binPath": "data/characters/Annie/skins/skin1.bin",
                            "chromas": [{"id": 10011, "binPath": "data/characters/Annie/skins/skin11.bin"}],
                        },
                    ],
                }
            ],
            "get_maps": lambda self: [
                {
                    "wad": {"root": "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client"},
                    "binPath": "data/maps/shipping/map11/map11.bin",
                }
            ],
            "get_champion": lambda self, _id: {},
            "get_map": lambda self, _id: {},
        },
    )()

    monkeypatch.setattr(m_remote, "urlopen", lambda _url: io.BytesIO(b"manifest-data"))

    class FakePatcherManifest:
        def __init__(self, *, file: Path, path: Path) -> None:  # noqa: ARG002
            self.path = Path(path)
            self.files = {}

    class FakeWADExtractor:
        def __init__(self, manifest) -> None:  # noqa: ANN001
            self.manifest = manifest

        def extract_files(self, wad_file_paths: dict[str, list[str]]) -> dict[str, dict[str, bytes | None]]:
            return {
                wad_path: {bin_path: f"{wad_path}|{bin_path}".encode() for bin_path in bin_paths}
                for wad_path, bin_paths in wad_file_paths.items()
            }

    monkeypatch.setattr(m_remote, "PatcherManifest", FakePatcherManifest)
    monkeypatch.setattr(m_remote, "WADExtractor", FakeWADExtractor)

    result = RemoteSnapshotPreparer(ctx=ctx).prepare_bin_inputs(reader=reader, target="all")

    assert result is not None
    assert result.extracted_file_count == EXPECTED_EXTRACTED_BIN_COUNT
    assert result.flag_file_path.exists()
    bin_input_root = ctx.paths.manifest_path / ctx.config.remote_snapshot.version / "bin_input"
    assert (bin_input_root / "data/characters/Annie/skins/skin0.bin").exists()
    assert (bin_input_root / "data/characters/Annie/skins/skin1.bin").exists()
    assert (bin_input_root / "data/characters/Annie/skins/skin11.bin").exists()
    assert (bin_input_root / "data/maps/shipping/map11/map11.bin").exists()


def test_remote_snapshot_preparer_prepare_extract_wads_only_downloads_language_wad_for_vo_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    reader = SimpleNamespace(
        ctx=ctx,
        get_audio_type=lambda category: "VO" if "VO" in category else "SFX",
        get_champion=lambda _id: {
            "id": 1,
            "wad": {
                "root": "Game/DATA/FINAL/Champions/Annie.wad.client",
                "zh_CN": "Game/DATA/FINAL/Champions/Annie.zh_CN.wad.client",
            },
        },
        get_champion_banks=lambda _id: {"skins": {"1000": {"CHARACTER_VO": [["path1"]]}}},
        get_map=lambda _id: {},
        get_map_banks=lambda _id: None,
        get_champions=lambda: [],
        get_maps=lambda: [],
    )
    monkeypatch.setattr(m_remote, "urlopen", lambda _url: io.BytesIO(b"manifest-data"))

    class FakeFile:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakePatcherManifest:
        def __init__(self, *, file: Path, path: Path) -> None:  # noqa: ARG002
            self.path = Path(path)
            names = [
                "DATA/FINAL/Champions/Annie.wad.client",
                "DATA/FINAL/Champions/Annie.zh_CN.wad.client",
            ]
            self.files = {name: FakeFile(name) for name in names}

        def file_output(self, file: FakeFile) -> str:
            return str(self.path / PurePosixPath(file.name))

        async def download_files_concurrently(self, files, raise_on_error=True):  # noqa: ARG002
            for file in files:
                output_path = Path(self.file_output(file))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(file.name.encode())
            return tuple(True for _ in files)

    monkeypatch.setattr(m_remote, "PatcherManifest", FakePatcherManifest)

    result = RemoteSnapshotPreparer(ctx=ctx).prepare_extract_wads(
        reader=reader,
        champion_ids=(1,),
        map_ids=None,
        include_champions=True,
        include_maps=False,
    )

    assert result is not None
    prepared_names = sorted(path.name for path in result.prepared_file_paths)
    assert prepared_names == ["Annie.zh_CN.wad.client"]
    prepared_file = ctx.config.game_path / "Game" / "DATA" / "FINAL" / "Champions" / "Annie.zh_CN.wad.client"
    assert prepared_file.exists()


def test_remote_snapshot_preparer_prepare_mapping_wads_downloads_root_and_language_wads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    reader = SimpleNamespace(
        ctx=ctx,
        get_champion=lambda _id: {
            "id": 1,
            "wad": {
                "root": "Game/DATA/FINAL/Champions/Annie.wad.client",
                "zh_CN": "Game/DATA/FINAL/Champions/Annie.zh_CN.wad.client",
            },
        },
        get_champion_banks=lambda _id: {
            "skins": {
                "1000": {
                    "CHARACTER_VO": [["voice_events.bnk"]],
                    "CHARACTER_SFX": [["sfx_events.bnk"]],
                }
            }
        },
        get_champion_events=lambda _id: {
            "skins": {
                "1000": {
                    "events": {
                        "CHARACTER_VO": ["Play_VO"],
                        "CHARACTER_SFX": ["Play_SFX"],
                    }
                }
            }
        },
        get_map=lambda _id: {},
        get_map_banks=lambda _id: None,
        get_map_events=lambda _id: None,
        get_champions=lambda: [],
        get_maps=lambda: [],
    )
    monkeypatch.setattr(m_remote, "urlopen", lambda _url: io.BytesIO(b"manifest-data"))

    class FakeFile:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakePatcherManifest:
        def __init__(self, *, file: Path, path: Path) -> None:  # noqa: ARG002
            self.path = Path(path)
            names = [
                "DATA/FINAL/Champions/Annie.wad.client",
                "DATA/FINAL/Champions/Annie.zh_CN.wad.client",
            ]
            self.files = {name: FakeFile(name) for name in names}

        def file_output(self, file: FakeFile) -> str:
            return str(self.path / PurePosixPath(file.name))

        async def download_files_concurrently(self, files, raise_on_error=True):  # noqa: ARG002
            for file in files:
                output_path = Path(self.file_output(file))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(file.name.encode())
            return tuple(True for _ in files)

    monkeypatch.setattr(m_remote, "PatcherManifest", FakePatcherManifest)

    result = RemoteSnapshotPreparer(ctx=ctx).prepare_mapping_wads(
        reader=reader,
        champion_ids=(1,),
        map_ids=None,
        include_champions=True,
        include_maps=False,
    )

    assert result is not None
    prepared_names = sorted(path.name for path in result.prepared_file_paths)
    assert prepared_names == ["Annie.wad.client", "Annie.zh_CN.wad.client"]


def test_facade_extract_prepares_remote_wads_before_unpack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_extract_wads(  # noqa: PLR0913
            self,
            *,
            reader,
            champion_ids,
            map_ids,
            include_champions,
            include_maps,
        ) -> None:
            assert reader is not None
            assert champion_ids is None
            assert map_ids is None
            assert include_champions is True
            assert include_maps is True
            call_order.append("prepare_extract")

    monkeypatch.setattr(m_facade, "RemoteSnapshotPreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx, version="16.5"))
    monkeypatch.setattr(m_facade, "unpack_audio_all", lambda **_kwargs: call_order.append("extract"))

    app.extract(OperationOptions())

    assert call_order == ["prepare_extract", "extract"]


def test_facade_mapping_prepares_remote_wads_before_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []
    wwiser_file = tmp_path / "wwiser.pyz"
    wwiser_file.write_bytes(b"dummy")
    app.ctx.config = AppConfig(
        game_path=ctx.config.game_path,
        output_path=ctx.config.output_path,
        game_region=ctx.config.game_region,
        source_mode=ctx.config.source_mode,
        remote_snapshot=ctx.config.remote_snapshot,
        wwiser_path=wwiser_file,
    )

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_mapping_wads(  # noqa: PLR0913
            self,
            *,
            reader,
            champion_ids,
            map_ids,
            include_champions,
            include_maps,
        ) -> None:
            assert reader is not None
            assert champion_ids is None
            assert map_ids is None
            assert include_champions is True
            assert include_maps is True
            call_order.append("prepare_mapping")

    monkeypatch.setattr(m_facade, "RemoteSnapshotPreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx, version="16.5"))
    monkeypatch.setattr(m_facade, "build_mapping_all", lambda **_kwargs: call_order.append("mapping"))

    app.mapping(OperationOptions())

    assert call_order == ["prepare_mapping", "mapping"]


def test_remote_snapshot_preparer_cleanup_tracked_artifacts_supports_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    ctx = AppContext(
        config=replace(ctx.config, exclude_types=(), include_types=("VO", "SFX", "MUSIC")),
        paths=ctx.paths,
        logger=ctx.logger,
        runtime_cache=ctx.runtime_cache,
    )
    monkeypatch.setattr(m_remote, "urlopen", lambda _url: io.BytesIO(b"manifest-data"))

    class FakeFile:
        def __init__(self, name: str) -> None:
            self.name = name

    class FakePatcherManifest:
        def __init__(self, *, file: Path, path: Path) -> None:
            self.file = file
            self.path = Path(path)
            names = [
                "plugins/rcp-be-lol-game-data/description.json",
                "plugins/rcp-be-lol-game-data/default-assets.wad",
                "plugins/rcp-be-lol-game-data/zh_CN-assets.wad",
                "DATA/FINAL/Champions/Annie.wad.client",
            ]
            self.files = {name: FakeFile(name) for name in names}

        def file_output(self, file: FakeFile) -> str:
            return str(self.path / PurePosixPath(file.name))

        async def download_files_concurrently(self, files, raise_on_error=True):  # noqa: ARG002
            for file in files:
                output_path = Path(self.file_output(file))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                if file.name.endswith("description.json"):
                    output_path.write_text(
                        json.dumps(
                            {
                                "riotMeta": {
                                    "globalAssetBundles": ["default-assets.wad"],
                                    "perLocaleAssetBundles": {"zh_CN": ["zh_CN-assets.wad"]},
                                }
                            }
                        ),
                        encoding="utf-8",
                    )
                else:
                    output_path.write_bytes(file.name.encode())
            return tuple(True for _ in files)

    class FakeWADExtractor:
        def __init__(self, manifest) -> None:  # noqa: ANN001
            self.manifest = manifest

        def extract_files(self, wad_file_paths: dict[str, list[str]]) -> dict[str, dict[str, bytes | None]]:
            return {
                wad_path: {bin_path: f"{wad_path}|{bin_path}".encode() for bin_path in bin_paths}
                for wad_path, bin_paths in wad_file_paths.items()
            }

    monkeypatch.setattr(m_remote, "PatcherManifest", FakePatcherManifest)
    monkeypatch.setattr(m_remote, "WADExtractor", FakeWADExtractor)

    preparer = RemoteSnapshotPreparer(ctx=ctx)
    lcu_result = preparer.prepare_lcu_game_data()
    reader = SimpleNamespace(
        get_champions=lambda: [
            {
                "alias": "Annie",
                "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
                "skins": [{"id": 1000, "binPath": "data/characters/Annie/skins/skin0.bin"}],
            }
        ],
        get_maps=lambda: [],
        get_champion=lambda _id: {},
        get_map=lambda _id: {},
        ctx=ctx,
    )
    bin_result = preparer.prepare_bin_inputs(reader=reader, target="skin")
    wad_result = preparer.prepare_extract_wads(
        reader=SimpleNamespace(
            ctx=ctx,
            get_audio_type=lambda _category: "SFX",
            get_champion=lambda _id: {
                "id": 1,
                "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
            },
            get_champion_banks=lambda _id: {"skins": {"1000": {"CHARACTER_SFX": [["path1"]]}}},
            get_map=lambda _id: {},
            get_map_banks=lambda _id: None,
            get_champions=lambda: [],
            get_maps=lambda: [],
        ),
        champion_ids=(1,),
        map_ids=None,
        include_champions=True,
        include_maps=False,
    )

    assert lcu_result.bundle_cache_paths
    assert bin_result is not None
    assert wad_result is not None

    cleanup_result = preparer.cleanup_tracked_artifacts(dry_run=True)

    assert cleanup_result["cached_lcu_wads"] == EXPECTED_CLEANUP_LCU_WADS
    assert cleanup_result["prepared_lcu_wads"] == EXPECTED_CLEANUP_LCU_WADS
    assert cleanup_result["bin_input_files"] == 1
    assert cleanup_result["bin_input_flags"] == 1
    assert cleanup_result["cached_game_wads"] == 1
    assert cleanup_result["prepared_game_wads"] == 1

    assert (ctx.paths.game_lcu_path / "description.json").exists()
    assert (ctx.paths.game_lcu_path / "default-assets.wad").exists()
    assert (ctx.paths.game_lcu_path / "zh_CN-assets.wad").exists()
    assert bin_result.flag_file_path.exists()
    assert any((ctx.paths.manifest_path / ctx.config.remote_snapshot.version / "bin_input").rglob("*"))
