import io
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from loguru import logger
from riotmanifest import DownloadError

import lol_audio_unpack.app.facade as m_facade
import lol_audio_unpack.app.remote_workflow as m_remote_workflow
import lol_audio_unpack.runtime.remote.preparer as m_remote
from lol_audio_unpack.app import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem
from lol_audio_unpack.app.results import EntityResult, ResultStatus, RunResult, StageResult
from lol_audio_unpack.app.types import (
    AppConfig,
    AppContext,
    AppPaths,
    OperationOptions,
    RemoteSnapshotConfig,
    SourceMode,
    WavOutputOptions,
)
from lol_audio_unpack.runtime.remote import RemotePreparer
from lol_audio_unpack.runtime.remote.cleanup import RemoteCleanupError

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
    )
    return AppContext(config=app_config, paths=app_paths, runtime_cache={})


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

    result = RemotePreparer(ctx=ctx).prepare_lcu_data()

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

    preparer = RemotePreparer(ctx=ctx)
    manifest_path = m_remote.remote_lcu.ensure_manifest_cached(
        manifest_url=ctx.config.remote_snapshot.lcu_manifest_url,
        manifest_cache_dir=preparer.lcu_manifest_cache_dir,
        headers=m_remote.MANIFEST_HEADERS,
        request_open=m_remote.urlopen,
    )

    assert manifest_path.exists()
    assert captured["url"] == ctx.config.remote_snapshot.lcu_manifest_url
    assert captured["user_agent"] == "Mozilla/5.0"


def test_facade_update_prepares_remote_snapshot_before_updaters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_lcu_data(self) -> None:
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

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataUpdater", FakeDataUpdater)
    monkeypatch.setattr(m_facade, "BinUpdater", FakeBinUpdater)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx))

    app.update(OperationOptions())

    assert call_order == ["prepare_lcu", "data", "prepare_bin", "bin"]


def test_facade_update_logs_start_and_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    info_messages: list[str] = []
    success_messages: list[str] = []

    class FakePreparer:
        def prepare_bin_inputs(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    class FakeBinUpdater:
        def __init__(self, force_update=False, process_events=True, ctx=None):  # noqa: ANN001, FBT002
            assert force_update is False
            assert process_events is True
            assert ctx is not None

        def update(self, *, target="all", champion_ids=None, map_ids=None) -> None:  # noqa: ANN001
            assert target == "all"
            assert champion_ids == ["1"]
            assert map_ids == ["11"]

    def _format_log(message: str, *args) -> str:
        return message.format(*args) if args else message

    def _fake_reader():
        return SimpleNamespace()

    monkeypatch.setattr(app, "prepare_update_data", lambda force_update=False: FakePreparer())  # type: ignore[method-assign]
    monkeypatch.setattr(app, "_get_reader", _fake_reader)  # type: ignore[method-assign]
    monkeypatch.setattr(m_facade, "BinUpdater", FakeBinUpdater)
    monkeypatch.setattr(
        m_facade,
        "logger",
        SimpleNamespace(
            info=lambda message, *args: info_messages.append(_format_log(message, *args)),
            success=lambda message, *args: success_messages.append(_format_log(message, *args)),
        ),
    )

    app.update(OperationOptions(champion_ids=(1,), map_ids=(11,)))

    assert info_messages == ["开始执行更新流程：target=all，英雄 1 个，地图 1 个，事件处理=开启"]
    assert success_messages == ["更新流程完成：target=all，英雄 1 个，地图 1 个"]


def test_prepare_update_data_warms_remote_data_once_per_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_lcu_data(self) -> None:
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

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataUpdater", FakeDataUpdater)
    monkeypatch.setattr(m_facade, "BinUpdater", FakeBinUpdater)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx))

    app.prepare_update_data()
    app.update(OperationOptions())

    assert call_order == ["prepare_lcu", "data", "prepare_lcu", "prepare_bin", "bin"]


def test_resolve_champion_ids_supports_aliases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)

    fake_reader = SimpleNamespace(
        get_champions=lambda: [
            {"id": 1, "alias": "Annie"},
            {"id": 103, "alias": "Ahri"},
        ]
    )

    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: fake_reader)

    champion_ids = app.resolve_champion_ids(["Annie", "ahri"])

    assert champion_ids == (1, 103)


def test_resolve_champion_ids_rejects_mixed_selectors(tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)

    with pytest.raises(ValueError, match="混用 ID 与 alias"):
        app.resolve_champion_ids([1, "Ahri"])


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
                    "id": 1,
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
                    "id": 11,
                    "wad": {"root": "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client"},
                    "binPath": "data/maps/shipping/map11/map11.bin",
                }
            ],
            "get_champion": lambda self, _id: self.get_champions()[0],
            "get_map": lambda self, _id: self.get_maps()[0],
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

    result = RemotePreparer(ctx=ctx).prepare_bin_inputs(reader=reader, target="all")

    assert result is not None
    assert result.extracted_file_count == EXPECTED_EXTRACTED_BIN_COUNT
    assert result.flag_file_path.exists()
    bin_input_root = ctx.paths.manifest_path / ctx.config.remote_snapshot.version / "bin_input"
    assert (bin_input_root / "data/characters/Annie/skins/skin0.bin").exists()
    assert (bin_input_root / "data/characters/Annie/skins/skin1.bin").exists()
    assert (bin_input_root / "data/characters/Annie/skins/skin11.bin").exists()
    assert (bin_input_root / "data/maps/shipping/map11/map11.bin").exists()


def test_remote_snapshot_preparer_logs_bin_input_plan_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    reader = SimpleNamespace()
    preparer = RemotePreparer(ctx=ctx)
    log_lines: list[str] = []

    monkeypatch.setattr(
        m_remote.remote_game,
        "build_bin_plan",
        lambda **_kwargs: {
            "Game/DATA/FINAL/Champions/Annie.wad.client": [
                "data/characters/Annie/skins/skin0.bin",
                "data/characters/Annie/skins/skin1.bin",
            ],
            "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client": [
                "data/maps/shipping/map11/map11.bin",
            ],
        },
    )
    monkeypatch.setattr(preparer, "_ensure_manifest_cached", lambda **_kwargs: tmp_path / "game.manifest")

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

    logger.enable("lol_audio_unpack")
    sink_id = logger.add(lambda message: log_lines.append(str(message).rstrip()), format="{level}|{message}")
    try:
        result = preparer.prepare_bin_inputs(reader=reader, target="all")
    finally:
        logger.remove(sink_id)

    assert result is not None
    assert any("INFO|开始准备远端 BIN 输入：target=all，WAD 2 个，BIN 3 个" in line for line in log_lines)
    assert any("INFO|远端 BIN 输入准备完成：共提取 3 个文件。" in line for line in log_lines)


def test_remote_snapshot_preparer_logs_entity_wad_scope_before_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    preparer = RemotePreparer(ctx=ctx)
    log_lines: list[str] = []

    monkeypatch.setattr(
        m_remote.remote_game,
        "build_extract_plan",
        lambda **_kwargs: {"Game/DATA/FINAL/Champions/Annie.wad.client"},
    )
    monkeypatch.setattr(
        m_remote.remote_game,
        "build_mapping_plan",
        lambda **_kwargs: {"Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client"},
    )
    monkeypatch.setattr(preparer, "_prepare_wads", lambda wad_paths: ("prepared", tuple(sorted(wad_paths))))

    logger.enable("lol_audio_unpack")
    sink_id = logger.add(lambda message: log_lines.append(str(message).rstrip()), format="{level}|{message}")
    try:
        result = preparer.prepare_entity_wads(
            reader=SimpleNamespace(),
            champion_ids=(1,),
            map_ids=(11,),
            include_champions=True,
            include_maps=True,
            need_extract=True,
            need_mapping=True,
        )
    finally:
        logger.remove(sink_id)

    assert result == (
        "prepared",
        (
            "Game/DATA/FINAL/Champions/Annie.wad.client",
            "Game/DATA/FINAL/Maps/Shipping/Map11/Map11.wad.client",
        ),
    )
    assert any("INFO|开始准备远端 GAME WAD：extract=开启，mapping=开启，目标 2 个" in line for line in log_lines)


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

    result = RemotePreparer(ctx=ctx).prepare_extract_wads(
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

    result = RemotePreparer(ctx=ctx).prepare_mapping_wads(
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

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx, version="16.5"))

    def fake_unpack_all(**_kwargs) -> StageResult:  # noqa: ANN003
        call_order.append("extract")
        return StageResult("extract")

    monkeypatch.setattr(m_facade, "unpack_all", fake_unpack_all)

    app.extract(OperationOptions())

    assert call_order == ["prepare_extract", "extract"]


def test_facade_mapping_prepares_remote_wads_before_mapping(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    call_order: list[str] = []

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

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx, version="16.5"))

    def fake_build_all(**_kwargs) -> StageResult:  # noqa: ANN003
        call_order.append("mapping")
        return StageResult("mapping")

    monkeypatch.setattr(m_facade, "build_all", fake_build_all)

    app.mapping(OperationOptions())

    assert call_order == ["prepare_mapping", "mapping"]


def test_facade_transcode_wav_uses_selected_entity_audio_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    calls: dict[str, object] = {}
    champion_dir = ctx.paths.audio_path / "16.5" / "champions" / "103-ahri"
    map_dir = ctx.paths.audio_path / "16.5" / "maps" / "11-howling-abyss"

    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: SimpleNamespace(ctx=ctx, version="16.5"))
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_type=kwargs["entity_type"],
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
    )
    app._resolve_audio_paths = lambda entity_data: {  # type: ignore[method-assign]
        ("champion", "103"): (champion_dir,),
        ("map", "11"): (map_dir,),
    }[(entity_data.entity_type, entity_data.entity_id)]
    monkeypatch.setattr(
        m_facade,
        "run_tree",
        lambda **kwargs: (
            calls.update(kwargs) or {"status": "success", "processed_file_count": 0, "failed_file_count": 0}
        ),
    )

    app.transcode_wav(
        OperationOptions(
            champion_ids=(103,),
            map_ids=(11,),
            wav_output=WavOutputOptions(enabled=True),
        )
    )

    assert calls["version"] == "16.5"
    audio_targets = calls["audio_targets"]
    assert tuple(target.root_path for target in audio_targets) == (champion_dir, map_dir)
    assert "audio_roots" not in calls


def test_facade_build_work_items_merges_extract_and_mapping_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])

    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)

    work_items = app.build_work_items(
        extract_options=OperationOptions(champion_ids=(1, 103)),
        mapping_options=OperationOptions(champion_ids=(103, 555)),
        extract_include_champions=True,
        mapping_include_champions=True,
    )

    assert work_items == [
        RemoteEntityWorkItem(entity_type="champion", entity_id=1, need_extract=True, need_mapping=False),
        RemoteEntityWorkItem(entity_type="champion", entity_id=103, need_extract=True, need_mapping=True),
        RemoteEntityWorkItem(entity_type="champion", entity_id=555, need_extract=False, need_mapping=True),
    ]


def test_facade_run_workflow_runs_per_entity_and_cleans_between_entities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    reader_contexts: list[AppContext] = []
    call_order: list[tuple] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **kwargs) -> None:  # noqa: ANN003
            call_order.append(("prepare", kwargs["champion_ids"], kwargs["need_extract"], kwargs["need_mapping"]))

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)

    def fake_reader(ctx) -> SimpleNamespace:  # noqa: ANN001
        reader_contexts.append(ctx)
        return reader

    monkeypatch.setattr(m_facade, "DataReader", fake_reader)
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    def fake_update(opts, *, target="all") -> StageResult:  # noqa: ANN001
        call_order.append(("update", opts.champion_ids, target))
        return StageResult("update")

    def fake_extract(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        call_order.append(("extract", opts.champion_ids, kwargs["prepare_remote"]))
        return StageResult("extract")

    def fake_mapping(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        call_order.append(("mapping", opts.champion_ids, kwargs["prepare_remote"]))
        return StageResult("mapping")

    app.update = fake_update  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.mapping = fake_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: call_order.append(("cleanup",))  # type: ignore[method-assign]

    app.run_workflow(
        update_options=OperationOptions(champion_ids=(1, 103)),
        update_target="skin",
        extract_options=OperationOptions(champion_ids=(1, 103)),
        mapping_options=OperationOptions(champion_ids=(103,)),
        extract_include_champions=True,
        mapping_include_champions=True,
    )

    assert call_order == [
        ("update", (1, 103), "skin"),
        ("cleanup",),
        ("prepare", (1,), True, False),
        ("extract", (1,), False),
        ("cleanup",),
        ("prepare", (103,), True, True),
        ("extract", (103,), False),
        ("mapping", (103,), False),
        ("cleanup",),
    ]
    assert reader_contexts == [ctx]


def test_facade_run_workflow_logs_completion_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    info_messages: list[str] = []
    success_messages: list[str] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    def _format_log(message: str, *args) -> str:
        return message.format(*args) if args else message

    monkeypatch.setattr(
        app,
        "build_work_items",
        lambda **_kwargs: [
            RemoteEntityWorkItem(entity_type="champion", entity_id=1, need_extract=True, need_mapping=False)
        ],
    )
    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )
    app.extract = lambda *_args, **_kwargs: StageResult("extract")  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(
        m_remote_workflow,
        "logger",
        SimpleNamespace(
            info=lambda message, *args: info_messages.append(_format_log(message, *args)),
            warning=lambda message, *args: info_messages.append(_format_log(message, *args)),
            success=lambda message, *args: success_messages.append(_format_log(message, *args)),
        ),
    )

    app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
    )

    assert any("remote 模式启用单位驱动执行，共 1 个实体工作项。" in line for line in info_messages)
    assert success_messages == ["remote 实体工作流完成：共处理 1 个实体工作项"]


def test_facade_run_workflow_invokes_callback_with_extract_and_mapping_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    callback_payloads: list[RemoteEntityCallbackPayload] = []

    entity_data = SimpleNamespace(
        entity_id="103",
        entity_name="阿狸",
        entity_alias="ahri",
        entity_title="九尾妖狐",
        entity_type="champion",
    )

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    extract_dir = ctx.paths.audio_path / "16.5" / "champions" / "103·ahri·阿狸·九尾妖狐"
    mapping_file = ctx.paths.hash_path / "16.5" / "champions" / "103.msgpack"

    def fake_extract(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (103,)
        assert kwargs["prepare_remote"] is False
        extract_dir.mkdir(parents=True, exist_ok=True)
        wem_path = extract_dir / "101.wem"
        wem_path.write_bytes(b"wem")
        return StageResult.from_entities(
            "extract",
            (EntityResult("champion", 103, ResultStatus.SUCCESS, artifacts=(str(wem_path),)),),
        )

    def fake_mapping(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (103,)
        assert kwargs["prepare_remote"] is False
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        mapping_file.write_bytes(b"mapping")
        return StageResult.from_entities(
            "mapping",
            (EntityResult("champion", 103, ResultStatus.SUCCESS, artifacts=(str(mapping_file),)),),
        )

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: entity_data  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.mapping = fake_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: None  # type: ignore[method-assign]

    app.run_workflow(
        extract_options=OperationOptions(champion_ids=(103,)),
        mapping_options=OperationOptions(champion_ids=(103,)),
        extract_include_champions=True,
        mapping_include_champions=True,
        on_entity_complete=callback_payloads.append,
    )

    assert callback_payloads == [
        RemoteEntityCallbackPayload(
            entity_type="champion",
            entity_id=103,
            audio_output_paths=(extract_dir,),
            mapping_output_path=mapping_file,
        )
    ]


def test_facade_run_workflow_callback_returns_multiple_audio_paths_when_grouped_by_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    ctx.config = replace(
        ctx.config,
        group_by_type=True,
        exclude_types=(),
        include_types=("VO", "SFX", "MUSIC"),
    )
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    callback_payloads: list[RemoteEntityCallbackPayload] = []

    entity_data = SimpleNamespace(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
    )

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    vo_dir = ctx.paths.audio_path / "16.5" / "VO" / "champions" / "1·annie·安妮·黑暗之女"
    sfx_dir = ctx.paths.audio_path / "16.5" / "SFX" / "champions" / "1·annie·安妮·黑暗之女"

    def fake_extract(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (1,)
        assert kwargs["prepare_remote"] is False
        vo_dir.mkdir(parents=True, exist_ok=True)
        sfx_dir.mkdir(parents=True, exist_ok=True)
        vo_path = vo_dir / "101.wem"
        sfx_path = sfx_dir / "102.wem"
        vo_path.write_bytes(b"vo")
        sfx_path.write_bytes(b"sfx")
        return StageResult.from_entities(
            "extract",
            (
                EntityResult(
                    "champion",
                    1,
                    ResultStatus.SUCCESS,
                    artifacts=(str(vo_path), str(sfx_path)),
                ),
            ),
        )

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: entity_data  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: None  # type: ignore[method-assign]

    app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        on_entity_complete=callback_payloads.append,
    )

    assert callback_payloads == [
        RemoteEntityCallbackPayload(
            entity_type="champion",
            entity_id=1,
            audio_output_paths=(vo_dir, sfx_dir),
            mapping_output_path=None,
        )
    ]


def test_facade_run_workflow_does_not_report_preexisting_output_without_artifact_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """仅目录存在不能证明本轮写入，远端完成回调必须保持静默。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    output_dir = ctx.paths.audio_path / "16.5" / "champions" / "1·annie·安妮·黑暗之女"
    output_dir.mkdir(parents=True)
    (output_dir / "stale.wem").write_bytes(b"old")
    callback_payloads: list[RemoteEntityCallbackPayload] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
    )
    app.extract = lambda *_args, **_kwargs: StageResult.from_entities(  # type: ignore[method-assign]
        "extract",
        (EntityResult("champion", 1, ResultStatus.SUCCESS),),
    )
    app.cleanup_remote_artifacts = lambda: None  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        on_entity_complete=callback_payloads.append,
    )

    assert result.status is ResultStatus.SUCCESS
    assert callback_payloads == []


def test_facade_run_workflow_retries_download_errors_before_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    download_retry_attempts = 3
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    call_order: list[tuple] = []
    attempts = {"prepare": 0}

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **kwargs) -> None:  # noqa: ANN003
            attempts["prepare"] += 1
            call_order.append(("prepare", attempts["prepare"], kwargs["champion_ids"]))
            if attempts["prepare"] < download_retry_attempts:
                raise DownloadError("network")

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    def fake_extract(opts, **kwargs) -> StageResult:  # noqa: ANN001, ANN003
        call_order.append(("extract", opts.champion_ids, kwargs["prepare_remote"]))
        return StageResult("extract")

    app.extract = fake_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: call_order.append(("cleanup",))  # type: ignore[method-assign]

    app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        download_retry_attempts=download_retry_attempts,
        entity_retry_attempts=2,
    )

    assert call_order == [
        ("prepare", 1, (1,)),
        ("prepare", 2, (1,)),
        ("prepare", 3, (1,)),
        ("extract", (1,), False),
        ("cleanup",),
    ]


@pytest.mark.parametrize("operation", ["extract", "mapping"])
def test_facade_run_workflow_retries_typed_entity_failures_before_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation: str,
) -> None:
    """实体阶段返回失败结果时，也要按完整实体重试契约重新执行。"""
    entity_retry_attempts = 3
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    attempts: list[int] = []
    cleanup_count = 0

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=kwargs["entity_id"],
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    def fake_operation(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        attempts.append(len(attempts) + 1)
        if len(attempts) < entity_retry_attempts:
            return StageResult.from_error(operation, RuntimeError(f"{operation} 暂时失败"))
        return StageResult(operation)

    def fake_cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    if operation == "extract":
        app.extract = fake_operation  # type: ignore[method-assign]
        workflow_options = {
            "extract_options": OperationOptions(champion_ids=(1,)),
            "extract_include_champions": True,
        }
    else:
        app.mapping = fake_operation  # type: ignore[method-assign]
        workflow_options = {
            "mapping_options": OperationOptions(champion_ids=(1,)),
            "mapping_include_champions": True,
        }
    app.cleanup_remote_artifacts = fake_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(entity_retry_attempts=entity_retry_attempts, **workflow_options)

    assert result.status is ResultStatus.SUCCESS
    assert attempts == list(range(1, entity_retry_attempts + 1))
    assert cleanup_count == entity_retry_attempts


def test_facade_run_workflow_retries_partial_entity_before_reporting_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """extract 成功但 mapping typed failed 时必须重试完整实体流程。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    output_dir = ctx.paths.audio_path / "16.5" / "champions" / "1·annie"
    mapping_file = ctx.paths.hash_path / "16.5" / "champions" / "1.msgpack"
    entity_retry_attempts = 2
    callbacks: list[RemoteEntityCallbackPayload] = []
    extract_attempts: list[int] = []
    mapping_attempts: list[int] = []
    cleanup_count = 0

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    def fake_extract(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        attempt = len(extract_attempts) + 1
        extract_attempts.append(attempt)
        output_dir.mkdir(parents=True, exist_ok=True)
        wem_path = output_dir / f"{attempt}.wem"
        wem_path.write_bytes(b"wem")
        return StageResult.from_entities(
            "extract",
            (EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=(str(wem_path),)),),
        )

    def fake_mapping(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        attempt = len(mapping_attempts) + 1
        mapping_attempts.append(attempt)
        if attempt == 1:
            return StageResult.from_error("mapping", RuntimeError("mapping typed failed"))
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        mapping_file.write_bytes(b"mapping")
        return StageResult.from_entities(
            "mapping",
            (EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=(str(mapping_file),)),),
        )

    def fake_cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=1,
        entity_name="安妮",
        entity_alias="annie",
        entity_title=None,
        entity_type="champion",
    )
    app._resolve_audio_paths = lambda _data: (output_dir,)  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.mapping = fake_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fake_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        mapping_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        mapping_include_champions=True,
        entity_retry_attempts=entity_retry_attempts,
        on_entity_complete=callbacks.append,
    )

    extract_result, mapping_result = result.stages
    assert result.status is ResultStatus.SUCCESS
    assert extract_result.entities[0].artifacts == (str(output_dir / "1.wem"), str(output_dir / "2.wem"))
    assert mapping_result.status is ResultStatus.SUCCESS
    assert extract_attempts == list(range(1, entity_retry_attempts + 1))
    assert mapping_attempts == list(range(1, entity_retry_attempts + 1))
    assert cleanup_count == entity_retry_attempts
    assert callbacks == [
        RemoteEntityCallbackPayload(
            entity_type="champion",
            entity_id=1,
            audio_output_paths=(output_dir,),
            mapping_output_path=mapping_file,
        )
    ]


def test_facade_run_workflow_keeps_prior_artifacts_after_mapping_exception_retries_exhaust(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """mapping 异常耗尽重试后，结果与回调仍保留此前 extract 的已确认产物。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    output_dir = ctx.paths.audio_path / "16.5" / "champions" / "1·annie"
    first_wem_path = output_dir / "1.wem"
    entity_retry_attempts = 2
    callbacks: list[RemoteEntityCallbackPayload] = []
    extract_attempts: list[int] = []
    mapping_attempts: list[int] = []
    cleanup_count = 0

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    def fake_extract(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        attempt = len(extract_attempts) + 1
        extract_attempts.append(attempt)
        if attempt == 1:
            output_dir.mkdir(parents=True, exist_ok=True)
            first_wem_path.write_bytes(b"wem")
            artifacts = (str(first_wem_path),)
        else:
            artifacts = ()
        return StageResult.from_entities(
            "extract",
            (EntityResult("champion", 1, ResultStatus.SUCCESS, artifacts=artifacts),),
        )

    def fail_mapping(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        mapping_attempts.append(len(mapping_attempts) + 1)
        raise RuntimeError("mapping root cause")

    def fake_cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=1,
        entity_name="安妮",
        entity_alias="annie",
        entity_title=None,
        entity_type="champion",
    )
    app._resolve_audio_paths = lambda _data: (output_dir,)  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.mapping = fail_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fake_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        mapping_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        mapping_include_champions=True,
        entity_retry_attempts=entity_retry_attempts,
        on_entity_complete=callbacks.append,
    )

    extract_result, mapping_result = result.stages
    assert result.status is ResultStatus.PARTIAL
    assert extract_result.status is ResultStatus.SUCCESS
    assert extract_result.entities[0].artifacts == (str(first_wem_path),)
    assert mapping_result.status is ResultStatus.FAILED
    assert mapping_result.entities[0].error_message == "mapping root cause"
    assert extract_attempts == list(range(1, entity_retry_attempts + 1))
    assert mapping_attempts == list(range(1, entity_retry_attempts + 1))
    assert cleanup_count == entity_retry_attempts
    assert callbacks == [
        RemoteEntityCallbackPayload(
            entity_type="champion",
            entity_id=1,
            audio_output_paths=(output_dir,),
            mapping_output_path=None,
        )
    ]


def test_facade_run_workflow_stops_immediately_on_typed_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """typed cancel 不得重试、启动当前 mapping 或继续后续实体。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    extract_calls: list[int] = []
    cleanup_count = 0

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    def cancel_extract(options, **_kwargs) -> StageResult:  # noqa: ANN001, ANN003
        entity_id = options.champion_ids[0]
        extract_calls.append(entity_id)
        return StageResult.cancelled(
            "extract",
            entities=(
                EntityResult(
                    "champion",
                    entity_id,
                    ResultStatus.CANCELLED,
                    artifacts=(str(tmp_path / "confirmed-before-cancel.wem"),),
                ),
            ),
        )

    def fail_mapping(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        pytest.fail("extract 取消后不应启动 mapping")

    def fake_cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=kwargs["entity_id"],
        entity_name=f"实体 {kwargs['entity_id']}",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )
    app.extract = cancel_extract  # type: ignore[method-assign]
    app.mapping = fail_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fake_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1, 2)),
        mapping_options=OperationOptions(champion_ids=(1, 2)),
        extract_include_champions=True,
        mapping_include_champions=True,
        entity_retry_attempts=3,
    )

    assert result.status is ResultStatus.CANCELLED
    assert [stage.stage for stage in result.stages] == ["extract"]
    assert result.stages[0].entities[0].artifacts == (str(tmp_path / "confirmed-before-cancel.wem"),)
    assert extract_calls == [1]
    assert cleanup_count == 1


def test_facade_run_workflow_keeps_prior_mapping_artifact_when_retry_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """重试中的 extract 取消时，保留前次已执行 mapping 的真实结果与产物。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    mapping_path = ctx.paths.hash_path / "16.5" / "champions" / "1.msgpack"
    extract_attempts: list[int] = []
    mapping_attempts: list[int] = []
    cleanup_count = 0

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    def fake_extract(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        attempt = len(extract_attempts) + 1
        extract_attempts.append(attempt)
        if attempt == 1:
            return StageResult.from_entities(
                "extract",
                (EntityResult("champion", 1, ResultStatus.SUCCESS),),
            )
        return StageResult.cancelled(
            "extract",
            entities=(EntityResult("champion", 1, ResultStatus.CANCELLED),),
        )

    def partial_mapping(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        mapping_attempts.append(len(mapping_attempts) + 1)
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        mapping_path.write_bytes(b"mapping")
        return StageResult.from_entities(
            "mapping",
            (
                EntityResult(
                    "champion",
                    1,
                    ResultStatus.PARTIAL,
                    error_type="MappingWarning",
                    artifacts=(str(mapping_path),),
                ),
            ),
        )

    def fake_cleanup() -> None:
        nonlocal cleanup_count
        cleanup_count += 1

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=1,
        entity_name="安妮",
        entity_alias="annie",
        entity_title=None,
        entity_type="champion",
    )
    app.extract = fake_extract  # type: ignore[method-assign]
    app.mapping = partial_mapping  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fake_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1, 2)),
        mapping_options=OperationOptions(champion_ids=(1, 2)),
        extract_include_champions=True,
        mapping_include_champions=True,
        entity_retry_attempts=3,
    )

    extract_result, mapping_result = result.stages
    assert result.status is ResultStatus.CANCELLED
    assert extract_result.status is ResultStatus.CANCELLED
    assert mapping_result.status is ResultStatus.PARTIAL
    assert mapping_result.entities[0].artifacts == (str(mapping_path),)
    assert extract_attempts == [1, 2]
    assert mapping_attempts == [1]
    assert cleanup_count == len(extract_attempts)


def test_facade_run_workflow_returns_failed_result_after_entity_retry_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    call_order: list[tuple] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **kwargs) -> None:  # noqa: ANN003
            call_order.append(("prepare", kwargs["champion_ids"]))

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    def fake_extract(opts, **kwargs) -> None:  # noqa: ANN001, ANN003
        call_order.append(("extract", opts.champion_ids, kwargs["prepare_remote"]))
        raise RuntimeError("bnk format changed")

    app.extract = fake_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: call_order.append(("cleanup",))  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        entity_retry_attempts=3,
    )

    assert result.status is ResultStatus.FAILED
    assert result.stages[-1].entities[0].error_message == "bnk format changed"

    assert call_order == [
        ("prepare", (1,)),
        ("extract", (1,), False),
        ("cleanup",),
        ("prepare", (1,)),
        ("extract", (1,), False),
        ("cleanup",),
        ("prepare", (1,)),
        ("extract", (1,), False),
        ("cleanup",),
    ]


def test_facade_run_workflow_stops_after_failed_update_and_always_cleans(tmp_path: Path) -> None:
    """失败的全局更新不能启动实体阶段，但必须执行清理。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))
    calls: list[str] = []

    def fake_update(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        calls.append("update")
        return StageResult.from_error("update", RuntimeError("更新失败"))

    def fake_extract(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        raise AssertionError("update 失败后不应执行 extract")

    app.update = fake_update  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: calls.append("cleanup")  # type: ignore[method-assign]

    result = app.run_workflow(
        update_options=OperationOptions(champion_ids=(1,)),
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
    )

    assert calls == ["update", "cleanup"]
    assert [stage.stage for stage in result.stages] == ["update"]
    assert result.status is ResultStatus.FAILED


def test_facade_run_workflow_converts_unexpected_update_error_and_cleans(tmp_path: Path) -> None:
    """全局 update 的普通异常必须结果化，且不能跳过清理。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))
    calls: list[str] = []

    def fail_update(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        calls.append("update")
        raise RuntimeError("更新根因")

    app.update = fail_update  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: calls.append("cleanup")  # type: ignore[method-assign]

    result = app.run_workflow(update_options=OperationOptions(champion_ids=(1,)))

    assert calls == ["update", "cleanup"]
    assert result.status is ResultStatus.FAILED
    assert result.stages == (StageResult.from_error("update", RuntimeError("更新根因")),)


def test_facade_run_workflow_keeps_update_error_when_cleanup_also_fails(tmp_path: Path) -> None:
    """清理失败必须附加为独立结果，不能覆盖 update 的根因。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))

    def fail_update(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        raise RuntimeError("更新根因")

    def fail_cleanup() -> None:
        raise OSError("清理根因")

    app.update = fail_update  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fail_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(update_options=OperationOptions(champion_ids=(1,)))

    update_result, cleanup_result = result.stages
    assert result.status is ResultStatus.FAILED
    assert update_result.error_message == "更新根因"
    assert cleanup_result.stage == "cleanup"
    assert cleanup_result.error_message == "清理根因"


@pytest.mark.parametrize("error", [KeyboardInterrupt("已取消"), SystemExit("退出")])
def test_facade_run_workflow_reraises_base_update_errors_after_cleanup(
    tmp_path: Path,
    error: BaseException,
) -> None:
    """取消和进程退出不能结果化，但必须先执行远端清理。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))
    calls: list[str] = []

    def interrupt_update(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        calls.append("update")
        raise error

    app.update = interrupt_update  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: calls.append("cleanup")  # type: ignore[method-assign]

    with pytest.raises(type(error)):
        app.run_workflow(update_options=OperationOptions(champion_ids=(1,)))

    assert calls == ["update", "cleanup"]


def test_facade_run_workflow_keeps_processing_after_entity_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """一个实体失败后，后续实体及其真实产物仍要正常汇总和回调。"""
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    output_dir = ctx.paths.audio_path / "16.5" / "champions" / "second"
    prepared: list[int] = []
    cleaned: list[int] = []
    progress: list[tuple[int, int, str]] = []
    callbacks: list[RemoteEntityCallbackPayload] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, *, champion_ids, **_kwargs) -> None:  # noqa: ANN003
            prepared.append(champion_ids[0])

    def fake_extract(opts, **_kwargs) -> StageResult:  # noqa: ANN001, ANN003
        entity_id = opts.champion_ids[0]
        if entity_id == 1:
            raise RuntimeError("首个实体失败")
        output_dir.mkdir(parents=True, exist_ok=True)
        wem_path = output_dir / "101.wem"
        wem_path.write_bytes(b"wem")
        return StageResult.from_entities(
            "extract",
            [
                EntityResult(
                    entity_type="champion",
                    entity_id=entity_id,
                    entity_name="第二个实体",
                    status=ResultStatus.PARTIAL,
                    artifacts=(str(wem_path),),
                )
            ],
        )

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=kwargs["entity_id"],
        entity_name=f"实体 {kwargs['entity_id']}",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )
    app._resolve_audio_paths = lambda _data: (output_dir,)  # type: ignore[method-assign]
    app.extract = fake_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: cleaned.append(len(cleaned) + 1)  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1, 2)),
        extract_include_champions=True,
        entity_retry_attempts=1,
        progress_callback=lambda current, total, message: progress.append((current, total, message)),
        on_entity_complete=callbacks.append,
    )

    extract_result = result.stages[0]
    assert result.status is ResultStatus.PARTIAL
    assert [entity.status for entity in extract_result.entities] == [ResultStatus.FAILED, ResultStatus.PARTIAL]
    assert prepared == [1, 2]
    assert cleaned == [1, 2]
    assert progress == [(2, 2, "实体 2 解包完成")]
    assert callbacks == [
        RemoteEntityCallbackPayload(
            entity_type="champion",
            entity_id=2,
            audio_output_paths=(output_dir,),
            mapping_output_path=None,
        )
    ]


def test_facade_run_workflow_keeps_entity_failure_when_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """清理失败只能追加 cleanup 结果，不能覆盖实体的根因。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **_kwargs) -> None:  # noqa: ANN003
            return None

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda _reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=kwargs["entity_id"],
        entity_name="失败实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    def fail_extract(*_args, **_kwargs) -> StageResult:  # noqa: ANN002, ANN003
        raise RuntimeError("解包根因")

    def fail_cleanup() -> None:
        raise OSError("清理根因")

    app.extract = fail_extract  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = fail_cleanup  # type: ignore[method-assign]

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=(1,)),
        extract_include_champions=True,
        entity_retry_attempts=1,
    )

    extract_result, cleanup_result = result.stages
    assert result.status is ResultStatus.FAILED
    assert extract_result.entities[0].error_message == "解包根因"
    assert cleanup_result.stage == "cleanup"
    assert cleanup_result.error_message == "清理根因"


def test_facade_run_workflow_returns_success_no_op_for_empty_work_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """空实体选择是稳定的成功 no-op，不能启动远端准备或完成回调。"""
    app = LolAudioUnpackApp(_build_remote_ctx(tmp_path))
    reader = SimpleNamespace(version="16.5", get_champions=lambda: [], get_maps=lambda: [])
    callbacks: list[RemoteEntityCallbackPayload] = []
    progress: list[tuple[int, int, str]] = []

    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)

    result = app.run_workflow(
        extract_options=OperationOptions(champion_ids=()),
        extract_include_champions=True,
        on_entity_complete=callbacks.append,
        progress_callback=lambda current, total, message: progress.append((current, total, message)),
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.stages == (StageResult("extract", note="没有待处理的远端实体。"),)
    assert callbacks == []
    assert progress == []


def test_facade_uses_canonical_workflow_names(tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)

    app.build_work_items = lambda **_kwargs: ["ok"]  # type: ignore[method-assign]
    app.run_workflow = lambda **_kwargs: RunResult()  # type: ignore[method-assign]

    assert app.build_work_items() == ["ok"]
    assert app.run_workflow().status is ResultStatus.SUCCESS


def test_remote_snapshot_preparer_cleanup_artifacts_supports_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_remote_ctx(tmp_path, game_region="zh_CN")
    ctx = AppContext(
        config=replace(ctx.config, exclude_types=(), include_types=("VO", "SFX", "MUSIC")),
        paths=ctx.paths,
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

    preparer = RemotePreparer(ctx=ctx)
    lcu_result = preparer.prepare_lcu_data()
    reader = SimpleNamespace(
        get_champions=lambda: [
            {
                "id": 1,
                "alias": "Annie",
                "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
                "skins": [{"id": 1000, "binPath": "data/characters/Annie/skins/skin0.bin"}],
            }
        ],
        get_maps=lambda: [],
        get_champion=lambda _id: {
            "id": 1,
            "alias": "Annie",
            "wad": {"root": "Game/DATA/FINAL/Champions/Annie.wad.client"},
            "skins": [{"id": 1000, "binPath": "data/characters/Annie/skins/skin0.bin"}],
        },
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

    cleanup_result = preparer.cleanup_artifacts(dry_run=True)

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


def test_remote_snapshot_preparer_cleanup_retains_failed_file_paths_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unlink 失败时保留失败登记项，同时继续清理其他已登记文件。"""
    ctx = _build_remote_ctx(tmp_path)
    preparer = RemotePreparer(ctx=ctx)
    blocked_path = tmp_path / "blocked.wad"
    removed_path = tmp_path / "removed.wad"
    missing_path = tmp_path / "missing.wad"
    blocked_path.write_bytes(b"blocked")
    removed_path.write_bytes(b"removed")
    preparer._track_cleanup_paths("cached_lcu_wads", [blocked_path, removed_path, missing_path])
    unlink = Path.unlink

    def fail_blocked_unlink(path: Path, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        if path == blocked_path:
            raise PermissionError("模拟文件占用")
        unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_blocked_unlink)

    with pytest.raises(RemoteCleanupError) as error_info:
        preparer.cleanup_artifacts()

    registry = ctx.runtime_cache[m_remote.CLEANUP_REGISTRY_KEY]
    assert not removed_path.exists()
    assert blocked_path.exists()
    assert registry["cached_lcu_wads"] == {str(blocked_path)}
    assert tuple(path for path, _error in error_info.value.failures) == (blocked_path,)
    assert isinstance(error_info.value.failures[0][1], PermissionError)

    monkeypatch.setattr(Path, "unlink", unlink)
    cleanup_counts = preparer.cleanup_artifacts()

    assert cleanup_counts["cached_lcu_wads"] == 1
    assert m_remote.CLEANUP_REGISTRY_KEY not in ctx.runtime_cache


def test_remote_snapshot_preparer_cleanup_retains_registry_when_empty_dir_cannot_be_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rmdir 失败时保留登记表，并继续删除同树的其余空目录。"""
    ctx = _build_remote_ctx(tmp_path)
    preparer = RemotePreparer(ctx=ctx)
    blocked_dir = preparer.prepared_lcu_root / "blocked"
    removed_dir = preparer.prepared_lcu_root / "removed"
    blocked_dir.mkdir(parents=True)
    removed_dir.mkdir()
    preparer._load_cleanup_registry()
    rmdir = Path.rmdir

    def fail_blocked_rmdir(path: Path, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        if path == blocked_dir:
            raise PermissionError("模拟目录占用")
        rmdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "rmdir", fail_blocked_rmdir)

    with pytest.raises(RemoteCleanupError) as error_info:
        preparer.cleanup_artifacts()

    assert blocked_dir.exists()
    assert not removed_dir.exists()
    assert m_remote.CLEANUP_REGISTRY_KEY in ctx.runtime_cache
    assert tuple(path for path, _error in error_info.value.failures) == (blocked_dir,)
    assert isinstance(error_info.value.failures[0][1], PermissionError)

    monkeypatch.setattr(Path, "rmdir", rmdir)
    preparer.cleanup_artifacts()

    assert not preparer.prepared_lcu_root.exists()
    assert m_remote.CLEANUP_REGISTRY_KEY not in ctx.runtime_cache
