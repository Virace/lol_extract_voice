"""`app.facade` 中 WAV 进度标签桥接的定向测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lol_audio_unpack.app.facade as facade_module
from lol_audio_unpack.app.facade import LolAudioUnpackApp
from lol_audio_unpack.app.resource_pack import ResourcePackWadRef, build_resource_pack_key
from lol_audio_unpack.app.types import OperationOptions, SourceMode, WavOutputOptions


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

    monkeypatch.setattr(app, "_create_reader", lambda: reader)
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

    app.transcode_wav(
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
    monkeypatch.setattr(app, "_create_reader", lambda: reader)
    monkeypatch.setattr(
        facade_module,
        "unpack_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(
        facade_module,
        "unpack_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])),
    )

    app.extract(
        OperationOptions(
            champion_ids=(1,),
            map_ids=(11,),
            special_targets=("champion:66600",),
        )
    )

    assert calls == [("champions", [1, 66600]), ("maps", [11])]


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
    monkeypatch.setattr(app, "_create_reader", lambda: reader)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: backend)
    monkeypatch.setattr(
        facade_module,
        "build_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(
        facade_module,
        "build_maps",
        lambda **kwargs: calls.append(("maps", kwargs["map_ids"])),
    )

    app.mapping(OperationOptions(champion_ids=(1,), map_ids=(11,)))

    assert calls == [("champions", [1]), ("maps", [11])]


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
    monkeypatch.setattr(app, "_create_reader", lambda: SimpleNamespace(version="16.16"))
    monkeypatch.setattr(facade_module, "BinUpdater", lambda **_kwargs: pytest.fail("不得执行默认 BinUpdater.update"))

    class _Discovery:
        def __init__(self, _ctx, *, reader=None):
            pass

        def discover(self, refs, *, version):
            captured["refs"] = refs
            captured["version"] = version
            return SimpleNamespace(status="complete", packs=(), cost={"candidateEntries": 0, "payloadReads": 0})

    monkeypatch.setattr(facade_module, "ResourcePackDiscovery", _Discovery)

    app.update(OperationOptions(resource_pack_wads=(ref,)))

    assert captured == {"refs": (ref,), "version": "16.16"}


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
    monkeypatch.setattr(app, "_create_reader", lambda: SimpleNamespace(version="16.16"))

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
    monkeypatch.setattr(app, "_create_reader", lambda: pytest.fail("stale WAD 不得进入 consumer"))

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
    monkeypatch.setattr(app, "_create_reader", SimpleNamespace)
    monkeypatch.setattr(facade_module, "unpack_resource_packs", lambda **kwargs: calls.append(kwargs["keys"]))
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
    monkeypatch.setattr(app, "_create_reader", SimpleNamespace)
    monkeypatch.setattr(
        facade_module,
        "unpack_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(facade_module, "unpack_maps", lambda **kwargs: calls.append(("maps", kwargs["map_ids"])))
    monkeypatch.setattr(
        facade_module,
        "unpack_resource_packs",
        lambda **kwargs: calls.append(("resource_packs", kwargs["keys"])),
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
    monkeypatch.setattr(app, "_create_reader", SimpleNamespace)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: "native")
    monkeypatch.setattr(facade_module, "build_resource_packs", lambda **kwargs: calls.append(kwargs["keys"]))
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
    monkeypatch.setattr(app, "_create_reader", SimpleNamespace)
    monkeypatch.setattr(app, "_describe_mapping_backend", lambda: "native")
    monkeypatch.setattr(
        facade_module,
        "build_champions",
        lambda **kwargs: calls.append(("champions", kwargs["champion_ids"])),
    )
    monkeypatch.setattr(facade_module, "build_maps", lambda **kwargs: calls.append(("maps", kwargs["map_ids"])))
    monkeypatch.setattr(
        facade_module,
        "build_resource_packs",
        lambda **kwargs: calls.append(("resource_packs", kwargs["keys"])),
    )

    app.mapping(OperationOptions(champion_ids=(1,), map_ids=(11,), special_targets=(key,)))

    assert calls == [("champions", [1]), ("maps", [11]), ("resource_packs", [key])]
