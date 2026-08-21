"""应用门面的阶段结果与目标分派定向测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, BrokenBarrierError
from types import SimpleNamespace

import pytest

import lol_audio_unpack.app.facade as facade_module
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.results import EntityResult, ResultStatus, StageResult
from lol_audio_unpack.app.types import OperationOptions, SourceMode, WavOutputOptions
from lol_audio_unpack.manager.errors import ArtifactWriteError


def _success_result(stage: str, entity_type: str = "champion", entity_id: int | str = 1) -> StageResult:
    return StageResult.from_entities(
        stage,
        (EntityResult(entity_type, entity_id, ResultStatus.SUCCESS),),
    )


def test_facade_lazily_reuses_and_explicitly_resets_its_reader(monkeypatch) -> None:
    """同一 app 复用 reader，显式失效后才创建新实例。"""
    expected_reader_count = 3
    ctx = SimpleNamespace()
    created: list[SimpleNamespace] = []

    def reader_factory(*, ctx) -> SimpleNamespace:  # noqa: ANN001
        reader = SimpleNamespace(ctx=ctx, sequence=len(created))
        created.append(reader)
        return reader

    monkeypatch.setattr(facade_module, "DataReader", reader_factory)
    app = LolAudioUnpackApp(ctx)
    other_app = LolAudioUnpackApp(ctx)

    assert created == []
    first = app._get_reader()
    assert app._get_reader() is first
    assert other_app._get_reader() is not first

    app._reset_reader()
    assert app._get_reader() is not first
    assert len(created) == expected_reader_count


def test_facade_reader_lazy_initialization_is_thread_safe(monkeypatch) -> None:
    """并发首次读取也只能构造并返回一个 app-owned reader。"""
    ctx = SimpleNamespace()
    start_barrier = Barrier(3)
    constructor_barrier = Barrier(2)
    created: list[SimpleNamespace] = []

    def reader_factory(*, ctx) -> SimpleNamespace:  # noqa: ANN001
        reader = SimpleNamespace(ctx=ctx)
        created.append(reader)
        try:
            # 无锁实现会让两个构造都到达；有锁实现只等待到超时后完成一次构造。
            constructor_barrier.wait(timeout=0.2)
        except BrokenBarrierError:
            pass
        return reader

    def get_reader(app: LolAudioUnpackApp):  # noqa: ANN202
        start_barrier.wait()
        return app._get_reader()

    monkeypatch.setattr(facade_module, "DataReader", reader_factory)
    app = LolAudioUnpackApp(ctx)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(get_reader, app) for _ in range(2)]
        start_barrier.wait()
        readers = [future.result() for future in futures]

    assert readers[0] is readers[1]
    assert created == [readers[0]]


@pytest.mark.parametrize("error_type", [None, OSError, RuntimeError])
def test_prepare_update_data_invalidates_reader_on_every_write_capable_exit(
    monkeypatch,
    error_type: type[Exception] | None,
) -> None:
    """直接 prepare 成功或异常退出后都不能继续复用旧 reader。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH),
        runtime_cache={},
    )
    created: list[SimpleNamespace] = []

    def reader_factory(*, ctx) -> SimpleNamespace:  # noqa: ANN001
        reader = SimpleNamespace(ctx=ctx, sequence=len(created))
        created.append(reader)
        return reader

    class FakeUpdater:
        def __init__(self, **_kwargs) -> None:
            pass

        def check_and_update(self) -> None:
            if error_type is not None:
                raise error_type("data write failed")

    monkeypatch.setattr(facade_module, "DataReader", reader_factory)
    monkeypatch.setattr(facade_module, "DataUpdater", FakeUpdater)
    app = LolAudioUnpackApp(ctx)
    stale_reader = app._get_reader()

    if error_type is not None:
        with pytest.raises(error_type, match="data write failed"):
            app.prepare_update_data()
    else:
        app.prepare_update_data()

    assert app._get_reader() is not stale_reader


@pytest.mark.parametrize(
    ("error_type", "expected_status"),
    [
        (None, ResultStatus.SUCCESS),
        (OSError, ResultStatus.FAILED),
        (RuntimeError, None),
    ],
)
def test_update_invalidates_reader_after_success_or_expected_failure(
    monkeypatch,
    error_type: type[Exception] | None,
    expected_status: ResultStatus | None,
) -> None:
    """BIN 写入路径无论成功或转为 failed result 都要失效 reader。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH),
        runtime_cache={},
    )
    created: list[SimpleNamespace] = []

    def reader_factory(*, ctx) -> SimpleNamespace:  # noqa: ANN001
        reader = SimpleNamespace(ctx=ctx, sequence=len(created))
        created.append(reader)
        return reader

    class FakeUpdater:
        def __init__(self, **_kwargs) -> None:
            pass

        def update(self, **_kwargs) -> None:
            if error_type is not None:
                raise error_type("banks write failed")

    monkeypatch.setattr(facade_module, "DataReader", reader_factory)
    monkeypatch.setattr(facade_module, "BinUpdater", FakeUpdater)
    app = LolAudioUnpackApp(ctx)
    monkeypatch.setattr(app, "prepare_update_data", lambda **_kwargs: None)
    stale_reader = app._get_reader()

    if error_type is RuntimeError:
        with pytest.raises(RuntimeError, match="banks write failed"):
            app.update(OperationOptions())
    else:
        result = app.update(OperationOptions())
        assert result.status is expected_status

    assert app._get_reader() is not stale_reader


@pytest.mark.parametrize("error_type", [None, OSError, RuntimeError])
def test_resource_pack_discovery_invalidates_reader_on_every_exit(
    monkeypatch,
    tmp_path: Path,
    error_type: type[Exception] | None,
) -> None:
    """独立 discovery 写入成功或失败后都要丢弃可能过期的资源 cache。"""
    game_root = tmp_path / "game"
    wad_path = game_root / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected")
    ref = ResourcePackWadRef.from_path(game_root, wad_path)
    ctx = SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_path=game_root))
    created: list[SimpleNamespace] = []
    discovery_readers: list[SimpleNamespace] = []

    def reader_factory(*, ctx) -> SimpleNamespace:  # noqa: ANN001
        reader = SimpleNamespace(ctx=ctx, version="16.16", sequence=len(created))
        created.append(reader)
        return reader

    class FakeDiscovery:
        def __init__(self, _ctx, *, reader) -> None:  # noqa: ANN001
            discovery_readers.append(reader)

        def discover(self, _refs, *, version):  # noqa: ANN001
            assert version == "16.16"
            if error_type is not None:
                raise error_type("resource write failed")
            return SimpleNamespace(status="complete", packs=(), cost={"candidateEntries": 0, "payloadReads": 0})

    monkeypatch.setattr(facade_module, "DataReader", reader_factory)
    monkeypatch.setattr(facade_module, "ResourcePackDiscovery", FakeDiscovery)
    app = LolAudioUnpackApp(ctx)
    stale_reader = app._get_reader()

    if error_type is not None:
        with pytest.raises(error_type, match="resource write failed"):
            app.discover_resource_packs(OperationOptions(resource_pack_wads=(ref,)))
    else:
        app.discover_resource_packs(OperationOptions(resource_pack_wads=(ref,)))

    assert discovery_readers[0] is not stale_reader
    assert app._get_reader() is not discovery_readers[0]


def test_transcode_wav_passes_entity_display_labels_to_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """独立 WAV stage 应将实体列表式名称传给 runtime 作为展示标签。"""
    app = LolAudioUnpackApp(SimpleNamespace())
    reader = SimpleNamespace(version="15.8")
    audio_root = tmp_path / "audios" / "15.8" / "champions" / "103-ahri"
    audio_root.mkdir(parents=True, exist_ok=True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(app, "_get_reader", lambda: reader)
    monkeypatch.setattr(
        app,
        "_build_entity_data",
        lambda *_args, **_kwargs: SimpleNamespace(entity_name="阿狸", entity_title="九尾妖狐"),
    )
    monkeypatch.setattr(app, "_resolve_audio_paths", lambda _entity_data: (audio_root,))
    monkeypatch.setattr(
        facade_module,
        "run_tree",
        lambda **kwargs: captured.update(kwargs) or {"status": "success"},
    )

    result = app.transcode_wav(
        OperationOptions(
            champion_ids=(103,),
            wav_output=WavOutputOptions(enabled=True),
        )
    )

    audio_targets = captured["audio_targets"]
    assert isinstance(audio_targets, tuple)
    assert len(audio_targets) == 1
    assert audio_targets[0].root_path == audio_root
    assert audio_targets[0].display_label == "阿狸·九尾妖狐"
    assert result.status is ResultStatus.SUCCESS
    assert result.entities == ()


def test_transcode_wav_records_wav_root_when_files_are_processed(monkeypatch, tmp_path: Path) -> None:
    """WAV runtime 处理过文件后，门面结果应提供稳定的批次产物证据。"""
    app = LolAudioUnpackApp(SimpleNamespace())
    wav_root = tmp_path / "wavs" / "15.8"
    monkeypatch.setattr(app, "_get_reader", lambda: SimpleNamespace(version="15.8"))
    monkeypatch.setattr(
        facade_module,
        "run_tree",
        lambda **_kwargs: {
            "status": "success",
            "processed_file_count": 2,
            "failed_file_count": 0,
            "wav_root": str(wav_root),
        },
    )

    result = app.transcode_wav(OperationOptions(wav_output=WavOutputOptions(enabled=True)))

    assert result.status is ResultStatus.SUCCESS
    assert result.entities == (EntityResult("wav", "batch", ResultStatus.SUCCESS, artifacts=(str(wav_root),)),)


@pytest.mark.parametrize(
    ("processed_count", "failed_count", "expected"),
    [
        (2, 1, ResultStatus.PARTIAL),
        (0, 1, ResultStatus.FAILED),
    ],
)
def test_transcode_wav_maps_runtime_warning_to_stage_result(
    monkeypatch,
    tmp_path: Path,
    processed_count: int,
    failed_count: int,
    expected: ResultStatus,
) -> None:
    app = LolAudioUnpackApp(SimpleNamespace())
    monkeypatch.setattr(app, "_get_reader", lambda: SimpleNamespace(version="15.8"))
    monkeypatch.setattr(
        facade_module,
        "run_tree",
        lambda **_kwargs: {
            "status": "warning",
            "processed_file_count": processed_count,
            "failed_file_count": failed_count,
            "wav_root": str(tmp_path / "wavs" / "15.8"),
        },
    )

    result = app.transcode_wav(OperationOptions(wav_output=WavOutputOptions(enabled=True)))

    assert result.status is expected
    if processed_count:
        assert result.entities[0].status is ResultStatus.PARTIAL
        assert result.entities[0].artifacts == (str(tmp_path / "wavs" / "15.8"),)
    else:
        assert result.entities == ()


def test_extract_runs_explicit_champions_and_maps_without_dropping_either_target(monkeypatch) -> None:
    """显式英雄与地图同时传入时，两个解包分支都应执行。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            include_types=("VO",),
            exclude_types=(),
            output_path=Path("output"),
            game_region="zh_CN",
        )
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[int]]] = []
    reader = SimpleNamespace()
    monkeypatch.setattr(app, "_get_reader", lambda: reader)
    monkeypatch.setattr(
        facade_module,
        "unpack_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])) or _success_result("extract"),
    )
    monkeypatch.setattr(
        facade_module,
        "unpack_maps",
        lambda **kwargs: (
            calls.append(("maps", kwargs["map_ids"]))
            or StageResult.from_entities(
                "extract",
                (EntityResult.from_error("map", 11, RuntimeError("map failed")),),
            )
        ),
    )

    result = app.extract(
        OperationOptions(
            champion_ids=(1,),
            map_ids=(11,),
            special_targets=("champion:66600",),
        )
    )

    assert calls == [("champions", [1, 66600]), ("maps", [11])]
    assert result.status is ResultStatus.PARTIAL
    assert tuple(entity.entity_id for entity in result.entities) == (1, 11)


def test_mapping_runs_explicit_champions_and_maps_without_dropping_either_target(monkeypatch) -> None:
    """显式英雄与地图同时传入时，两个映射分支都应执行。"""
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            game_region="zh_CN",
        ),
        paths=SimpleNamespace(cache_path=Path("cache"), hash_path=Path("hashes")),
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[int]]] = []
    reader = SimpleNamespace()
    backend = "native"
    monkeypatch.setattr(app, "_get_reader", lambda: reader)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: backend)
    monkeypatch.setattr(
        facade_module,
        "build_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])) or _success_result("mapping"),
    )
    monkeypatch.setattr(
        facade_module,
        "build_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])) or _success_result("mapping", "map", 11),
    )

    result = app.mapping(OperationOptions(champion_ids=(1,), map_ids=(11,)))

    assert calls == [("champions", [1]), ("maps", [11])]
    assert result.status is ResultStatus.SUCCESS
    assert tuple(entity.entity_id for entity in result.entities) == (1, 11)


def test_facade_rejects_remote_special_targets_before_resource_preparation() -> None:
    """门面直接调用也必须在远端资源准备前拒绝特殊内容。"""
    app = LolAudioUnpackApp(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.REMOTE_SNAPSHOT)))

    with pytest.raises(ValueError, match="特殊内容仅支持本地客户端资源"):
        app.extract(OperationOptions(special_targets=("champion:66600",)))


def test_update_with_resource_pack_wad_skips_default_entity_update_and_runs_discovery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """只选择 resource-pack WAD 时不能退化为全量英雄/地图 update。"""
    game_root = tmp_path / "game"
    wad_path = game_root / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected")
    ref = ResourcePackWadRef.from_path(game_root, wad_path)
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_path=game_root),
        paths=SimpleNamespace(manifest_path=tmp_path / "manifest"),
    )
    app = LolAudioUnpackApp(ctx)
    captured: dict[str, object] = {}

    monkeypatch.setattr(app, "prepare_update_data", lambda **_kwargs: None)
    monkeypatch.setattr(app, "_get_reader", lambda: SimpleNamespace(version="16.16"))
    monkeypatch.setattr(facade_module, "BinUpdater", lambda **_kwargs: pytest.fail("不得执行默认 BinUpdater.update"))

    class _Discovery:
        def __init__(self, _ctx, *, reader=None):
            pass

        def discover(self, refs, *, version):
            captured["refs"] = refs
            captured["version"] = version
            return SimpleNamespace(status="complete", packs=(), cost={"candidateEntries": 0, "payloadReads": 0})

    monkeypatch.setattr(facade_module, "ResourcePackDiscovery", _Discovery)

    result = app.update(OperationOptions(resource_pack_wads=(ref,)))

    assert captured == {"refs": (ref,), "version": "16.16"}
    assert result.status is ResultStatus.SUCCESS


def test_update_maps_artifact_write_failure_to_failed_stage(monkeypatch, tmp_path: Path) -> None:
    app = LolAudioUnpackApp(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH)))
    error = ArtifactWriteError(tmp_path / "data.msgpack", "replace")
    monkeypatch.setattr(app, "prepare_update_data", lambda **_kwargs: (_ for _ in ()).throw(error))

    result = app.update(OperationOptions())

    assert result.status is ResultStatus.FAILED
    assert result.error_type == "ArtifactWriteError"


def test_update_runs_explicit_entity_update_and_resource_pack_discovery_together(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """显式英雄/地图 target 与 selected WAD 可以在同一次 update 中各自执行。"""
    game_root = tmp_path / "game"
    wad_path = game_root / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected")
    ref = ResourcePackWadRef.from_path(game_root, wad_path)
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_path=game_root),
        paths=SimpleNamespace(manifest_path=tmp_path / "manifest"),
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[str] = []

    monkeypatch.setattr(app, "prepare_update_data", lambda **_kwargs: None)
    monkeypatch.setattr(app, "_get_reader", lambda: SimpleNamespace(version="16.16"))

    class _Updater:
        def __init__(self, **_kwargs):
            calls.append("updater-created")

        def update(self, **kwargs):
            calls.append(f"updater:{kwargs['champion_ids']}")

    class _Discovery:
        def __init__(self, _ctx, *, reader=None):
            pass

        def discover(self, _refs, *, version):
            calls.append(f"discovery:{version}")
            return SimpleNamespace(status="complete", packs=(), cost={"candidateEntries": 0, "payloadReads": 0})

    monkeypatch.setattr(facade_module, "BinUpdater", _Updater)
    monkeypatch.setattr(facade_module, "ResourcePackDiscovery", _Discovery)

    app.update(OperationOptions(champion_ids=(1,), resource_pack_wads=(ref,)), target="skin")

    assert calls == ["updater-created", "updater:['1']", "discovery:16.16"]


def test_update_does_not_route_resource_pack_special_target_to_default_entity_update(monkeypatch) -> None:
    """已发现的 resource-pack key 也不能触发英雄/地图默认全量 update。"""
    ctx = SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH))
    app = LolAudioUnpackApp(ctx)
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")

    monkeypatch.setattr(app, "prepare_update_data", lambda **_kwargs: None)
    monkeypatch.setattr(facade_module, "BinUpdater", lambda **_kwargs: pytest.fail("不得执行默认 BinUpdater.update"))

    app.update(OperationOptions(special_targets=(key,)))


def test_facade_rejects_remote_resource_pack_wad_before_update_preparation() -> None:
    """remote 模式不得把 selected-WAD 发送到本地 discovery 边界。"""
    app = LolAudioUnpackApp(SimpleNamespace(config=SimpleNamespace(source_mode=SourceMode.REMOTE_SNAPSHOT)))
    ref = ResourcePackWadRef("Game/DATA/FINAL/TFTCommon.wad.client", 1, 1)

    with pytest.raises(ValueError, match="资源包发现仅支持本地客户端资源"):
        app.update(OperationOptions(resource_pack_wads=(ref,)))


def test_facade_revalidates_resource_pack_wad_before_extract(monkeypatch, tmp_path: Path) -> None:
    """任务入队后 WAD 发生变化时，extract 必须在任何 consumer 前失败。"""
    game_root = tmp_path / "game"
    wad_path = game_root / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"selected")
    ref = ResourcePackWadRef.from_path(game_root, wad_path)
    wad_path.write_bytes(b"changed-size")
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_path=game_root),
    )
    app = LolAudioUnpackApp(ctx)
    monkeypatch.setattr(app, "_get_reader", lambda: pytest.fail("stale WAD 不得进入 consumer"))

    with pytest.raises(ValueError, match="已变化"):
        app.extract(OperationOptions(resource_pack_wads=(ref,)))


def test_extract_resource_pack_only_uses_special_consumer_without_all_fallback(monkeypatch) -> None:
    """pack-only extract 必须走专用 consumer，不能回退 unpack_all。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            include_types=("SFX",),
            exclude_types=(),
            output_path=Path("output"),
            game_region="zh_CN",
        )
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[list[str]] = []
    monkeypatch.setattr(app, "_get_reader", SimpleNamespace)
    monkeypatch.setattr(
        facade_module,
        "unpack_resource_packs",
        lambda **kwargs: calls.append(kwargs["keys"]) or _success_result("extract", "resource_pack", kwargs["keys"][0]),
    )
    monkeypatch.setattr(facade_module, "unpack_all", lambda **_kwargs: pytest.fail("不得回退 unpack_all"))

    app.extract(OperationOptions(special_targets=(key,)))

    assert calls == [[key]]


def test_extract_dispatches_champion_map_and_resource_pack_together(monkeypatch) -> None:
    """mixed extract 应执行三类显式目标，而非只保留 champion/map。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            source_mode=SourceMode.LOCAL_PATH,
            include_types=("SFX",),
            exclude_types=(),
            output_path=Path("output"),
            game_region="zh_CN",
        )
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[object]]] = []
    monkeypatch.setattr(app, "_get_reader", SimpleNamespace)
    monkeypatch.setattr(
        facade_module,
        "unpack_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])) or _success_result("extract"),
    )
    monkeypatch.setattr(
        facade_module,
        "unpack_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])) or _success_result("extract", "map", 11),
    )
    monkeypatch.setattr(
        facade_module,
        "unpack_resource_packs",
        lambda **kwargs: (
            calls.append(("resource_packs", kwargs["keys"]))
            or _success_result("extract", "resource_pack", kwargs["keys"][0])
        ),
    )

    app.extract(OperationOptions(champion_ids=(1,), map_ids=(11,), special_targets=(key,)))

    assert calls == [("champions", [1]), ("maps", [11]), ("resource_packs", [key])]


def test_mapping_resource_pack_only_uses_special_consumer_without_all_fallback(monkeypatch) -> None:
    """pack-only mapping 必须走专用 consumer，不能回退 build_all。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_region="zh_CN"),
        paths=SimpleNamespace(cache_path=Path("cache"), hash_path=Path("hashes")),
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[list[str]] = []
    monkeypatch.setattr(app, "_get_reader", SimpleNamespace)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: "native")
    monkeypatch.setattr(
        facade_module,
        "build_resource_packs",
        lambda **kwargs: calls.append(kwargs["keys"]) or _success_result("mapping", "resource_pack", kwargs["keys"][0]),
    )
    monkeypatch.setattr(facade_module, "build_all", lambda **_kwargs: pytest.fail("不得回退 build_all"))

    app.mapping(OperationOptions(special_targets=(key,)))

    assert calls == [[key]]


def test_mapping_dispatches_champion_map_and_resource_pack_together(monkeypatch) -> None:
    """mixed mapping 应执行三类显式目标。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    ctx = SimpleNamespace(
        config=SimpleNamespace(source_mode=SourceMode.LOCAL_PATH, game_region="zh_CN"),
        paths=SimpleNamespace(cache_path=Path("cache"), hash_path=Path("hashes")),
    )
    app = LolAudioUnpackApp(ctx)
    calls: list[tuple[str, list[object]]] = []
    monkeypatch.setattr(app, "_get_reader", SimpleNamespace)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: "native")
    monkeypatch.setattr(
        facade_module,
        "build_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])) or _success_result("mapping"),
    )
    monkeypatch.setattr(
        facade_module,
        "build_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])) or _success_result("mapping", "map", 11),
    )
    monkeypatch.setattr(
        facade_module,
        "build_resource_packs",
        lambda **kwargs: (
            calls.append(("resource_packs", kwargs["keys"]))
            or _success_result("mapping", "resource_pack", kwargs["keys"][0])
        ),
    )

    app.mapping(OperationOptions(champion_ids=(1,), map_ids=(11,), special_targets=(key,)))

    assert calls == [("champions", [1]), ("maps", [11]), ("resource_packs", [key])]
