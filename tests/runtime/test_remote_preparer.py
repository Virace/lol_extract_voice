import io
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from loguru import logger
from riotmanifest import DownloadError

import lol_audio_unpack.app.facade as m_facade
import lol_audio_unpack.runtime.remote.preparer as m_remote
from lol_audio_unpack.app import create_app_context
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem
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
    monkeypatch.setattr(app, "_create_reader", _fake_reader)  # type: ignore[method-assign]
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
    monkeypatch.setattr(m_facade, "unpack_all", lambda **_kwargs: call_order.append("extract"))

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
    monkeypatch.setattr(m_facade, "build_all", lambda **_kwargs: call_order.append("mapping"))

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
    )
    app._resolve_audio_paths = lambda entity_data: {  # type: ignore[method-assign]
        ("champion", "103"): (champion_dir,),
        ("map", "11"): (map_dir,),
    }[(entity_data.entity_type, entity_data.entity_id)]
    monkeypatch.setattr(
        m_facade,
        "run_tree",
        lambda **kwargs: calls.update(kwargs) or {"status": "success", "processed_file_count": 0, "failed_file_count": 0},
    )

    app.transcode_wav(
        OperationOptions(
            champion_ids=(103,),
            map_ids=(11,),
            wav_output=WavOutputOptions(enabled=True),
        )
    )

    assert calls["version"] == "16.5"
    assert calls["audio_roots"] == (champion_dir, map_dir)


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
    call_order: list[tuple] = []

    class FakePreparer:
        def __init__(self, *, ctx) -> None:  # noqa: ANN001
            assert ctx is not None

        def prepare_entity_wads(self, **kwargs) -> None:  # noqa: ANN003
            call_order.append(("prepare", kwargs["champion_ids"], kwargs["need_extract"], kwargs["need_mapping"]))

    monkeypatch.setattr(m_facade, "RemotePreparer", FakePreparer)
    monkeypatch.setattr(m_facade, "DataReader", lambda ctx: reader)
    app._build_entity_data = lambda reader, **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        entity_id=str(kwargs["entity_id"]),
        entity_name="测试实体",
        entity_alias="test",
        entity_title=None,
        entity_type=kwargs["entity_type"],
    )

    app.update = lambda opts, *, target="all": call_order.append(("update", opts.champion_ids, target))  # type: ignore[method-assign]
    app.extract = (  # type: ignore[method-assign]
        lambda opts, **kwargs: call_order.append(("extract", opts.champion_ids, kwargs["prepare_remote"]))
    )
    app.mapping = (  # type: ignore[method-assign]
        lambda opts, **kwargs: call_order.append(("mapping", opts.champion_ids, kwargs["prepare_remote"]))
    )
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
    app.extract = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    app.cleanup_remote_artifacts = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(
        m_facade,
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

    def fake_extract(opts, **kwargs) -> None:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (103,)
        assert kwargs["prepare_remote"] is False
        extract_dir.mkdir(parents=True, exist_ok=True)

    def fake_mapping(opts, **kwargs) -> None:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (103,)
        assert kwargs["prepare_remote"] is False
        mapping_file.parent.mkdir(parents=True, exist_ok=True)
        mapping_file.write_bytes(b"mapping")

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

    def fake_extract(opts, **kwargs) -> None:  # noqa: ANN001, ANN003
        assert opts.champion_ids == (1,)
        assert kwargs["prepare_remote"] is False
        vo_dir.mkdir(parents=True, exist_ok=True)
        sfx_dir.mkdir(parents=True, exist_ok=True)

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
    app.extract = lambda opts, **kwargs: call_order.append(("extract", opts.champion_ids, kwargs["prepare_remote"]))  # type: ignore[method-assign]
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


def test_facade_run_workflow_raises_after_entity_retry_threshold(
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

    with pytest.raises(RuntimeError, match="当前解包脚本可能无法正常解包"):
        app.run_workflow(
            extract_options=OperationOptions(champion_ids=(1,)),
            extract_include_champions=True,
            entity_retry_attempts=3,
        )

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


def test_facade_uses_canonical_workflow_names(tmp_path: Path) -> None:
    ctx = _build_remote_ctx(tmp_path)
    app = LolAudioUnpackApp(ctx)

    app.build_work_items = lambda **_kwargs: ["ok"]  # type: ignore[method-assign]
    app.run_workflow = lambda **_kwargs: None  # type: ignore[method-assign]

    assert app.build_work_items() == ["ok"]
    assert app.run_workflow() is None


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
