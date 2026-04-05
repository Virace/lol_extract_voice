from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack import mapping as m_mapping
from lol_audio_unpack import unpack as m_unpack
from lol_audio_unpack.app.types import AppConfig, AppContext, AppPaths
from lol_audio_unpack.mapping import batch as mapping_batch
from lol_audio_unpack.mapping import session as mapping_session
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import bp_vo as unpack_bp_vo
from lol_audio_unpack.utils.path_constants import format_entity_folder_name, format_sub_entity_folder_name

pytestmark = pytest.mark.unit


def _build_ctx(
    tmp_path: Path,
    *,
    game_region: str = "zh_CN",
    group_by_type: bool = False,
    with_bp_vo: bool = False,
    wwiser_path: Path | None = None,
) -> AppContext:
    game_path = tmp_path / "game"
    output_path = tmp_path / "output"
    app_config = AppConfig(
        game_path=game_path,
        output_path=output_path,
        game_region=game_region,
        group_by_type=group_by_type,
        with_bp_vo=with_bp_vo,
        wwiser_path=wwiser_path,
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
    return AppContext(config=app_config, paths=app_paths)


def test_audio_entity_from_champion_uses_ctx_region_and_game_path(tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path, game_region="en_US")
    wad_file = ctx.game_path / "Game" / "en.wad.client"
    root_wad_file = ctx.game_path / "Game" / "root.wad.client"
    wad_file.parent.mkdir(parents=True, exist_ok=True)
    wad_file.write_bytes(b"wad")
    root_wad_file.write_bytes(b"root-wad")

    reader = SimpleNamespace(
        get_champion=lambda _id: {
            "id": 1,
            "alias": "Annie",
            "names": {"zh_CN": "安妮", "en_US": "Annie"},
            "titles": {"zh_CN": "黑暗之女", "en_US": "The Dark Child"},
            "skins": [{"id": 1000, "isBase": True, "skinNames": {"zh_CN": "基础皮肤", "en_US": "Base Skin"}}],
            "wad": {"root": "Game/root.wad.client", "en_US": "Game/en.wad.client"},
        },
        get_champion_banks=lambda _id: {"skins": {"1000": {"CHARACTER_VO": [["Game/en_events.bnk"]]}}},
        get_champion_events=lambda _id: {"skins": {"1000": {"events": {}}}},
    )

    entity_data = AudioEntityData.from_champion(1, reader, ctx=ctx)

    assert ctx.game_region == "en_US"
    assert entity_data.entity_name == "Annie"
    assert entity_data.wad_language == "Game/en.wad.client"
    assert entity_data.get_wad_path("VO", ctx=ctx) == wad_file
    assert entity_data.get_wad_path("SFX", ctx=ctx) == root_wad_file


def test_generate_output_path_supports_ctx_grouping(tmp_path: Path) -> None:
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={"1000": {"name": "基础皮肤", "categories": {}}},
        wad_root="Game/root.wad.client",
        wad_language="Game/zh.wad.client",
    )

    by_type_ctx = _build_ctx(tmp_path, group_by_type=True)
    by_entity_ctx = _build_ctx(tmp_path, group_by_type=False)

    path_by_type = m_unpack.generate_output_path(entity_data, "1000", "VO", ctx=by_type_ctx)
    path_by_entity = m_unpack.generate_output_path(entity_data, "1000", "VO", ctx=by_entity_ctx)
    relative_path = (
        Path("champions")
        / format_entity_folder_name("1", "annie", "安妮", "黑暗之女")
        / format_sub_entity_folder_name("1000", "基础皮肤")
    )

    assert path_by_type == by_type_ctx.paths.audio_path / "VO" / relative_path
    assert path_by_entity == by_entity_ctx.paths.audio_path / relative_path / "VO"


def test_attach_bp_vo_to_champion_uses_ctx_without_global_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "16.3"
    ctx = _build_ctx(tmp_path, game_region="zh_CN", with_bp_vo=True)

    manifest_root = ctx.paths.manifest_path
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo").mkdir(parents=True, exist_ok=True)
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo").mkdir(parents=True, exist_ok=True)

    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-ban-vo" / "1.ogg").write_bytes(b"ban")
    (manifest_root / version / "lobby_vo" / "zh_CN" / "champion-choose-vo" / "1.ogg").write_bytes(b"choose")

    monkeypatch.setattr(unpack_bp_vo.os, "link", lambda _src, _dst: (_ for _ in ()).throw(OSError("no link")))

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="安妮",
        entity_alias="annie",
        entity_title="黑暗之女",
        entity_type="champion",
        sub_entities={},
        wad_root="Game/root.wad.client",
        wad_language=None,
    )
    reader = SimpleNamespace(version=version)

    unpack_bp_vo.attach_bp_vo(entity_data, reader, ctx=ctx)

    entity_folder = format_entity_folder_name("1", "annie", "安妮", "黑暗之女")
    target_dir = ctx.paths.audio_path / version / "champions" / entity_folder / "BP_VO"
    assert (target_dir / "ban.ogg").read_bytes() == b"ban"
    assert (target_dir / "choose.ogg").read_bytes() == b"choose"


def test_execute_tasks_defaults_to_native_hirc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx = _build_ctx(tmp_path)
    captured: dict[str, object] = {}

    def fail_wwiser_manager(_path: Path | str | None) -> object:
        pytest.fail("默认 mapping 不应创建 WwiserManager")

    def fake_build_champion_mapping(*args, **kwargs) -> dict[str, object]:
        captured["wwiser_manager"] = args[2]
        captured["ctx"] = kwargs.get("ctx")
        return {}

    monkeypatch.setattr(mapping_session, "WwiserManager", fail_wwiser_manager)
    monkeypatch.setattr(mapping_batch, "build_champion", fake_build_champion_mapping)

    reader = SimpleNamespace()
    m_mapping.execute_tasks([("champion", 1, "英雄ID 1")], reader, max_workers=1, ctx=ctx)

    assert captured["wwiser_manager"] is None
    assert captured["ctx"] == ctx


def test_execute_tasks_passes_wwiser_manager_and_ctx_to_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wwiser_file = tmp_path / "wwiser.pyz"
    wwiser_file.write_bytes(b"dummy")
    ctx = _build_ctx(tmp_path, wwiser_path=wwiser_file)

    captured: dict[str, object] = {}
    wwiser_manager = object()

    def fake_wwiser_manager(path: Path | str | None) -> object:
        captured["wwiser_path"] = path
        return wwiser_manager

    def fake_build_champion_mapping(*args, **kwargs) -> dict[str, object]:
        captured["wwiser_manager"] = args[2]
        captured["ctx"] = kwargs.get("ctx")
        return {}

    monkeypatch.setattr(mapping_session, "WwiserManager", fake_wwiser_manager)
    monkeypatch.setattr(mapping_batch, "build_champion", fake_build_champion_mapping)

    reader = SimpleNamespace()
    m_mapping.execute_tasks([("champion", 1, "英雄ID 1")], reader, max_workers=1, ctx=ctx)

    assert captured["wwiser_path"] == wwiser_file
    assert captured["wwiser_manager"] is wwiser_manager
    assert captured["ctx"] == ctx


def test_mapping_execute_tasks_uses_warning_summary_for_partial_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ctx = _build_ctx(tmp_path)
    infos: list[str] = []
    warnings: list[str] = []
    successes: list[str] = []
    errors: list[str] = []
    opt_calls: list[dict[str, object]] = []

    def _record_warning(message: str) -> None:
        warnings.append(message)

    def _opt_logger(**kwargs):
        opt_calls.append(kwargs)
        return SimpleNamespace(warning=_record_warning)

    fake_logger = SimpleNamespace(
        info=infos.append,
        debug=lambda _message: None,
        success=successes.append,
        warning=warnings.append,
        error=errors.append,
        opt=_opt_logger,
    )

    def _fake_unpack_champion(*_args, **_kwargs) -> None:
        return None

    def _fail_unpack_map(*_args, **_kwargs) -> None:
        raise RuntimeError("map boom")

    reader = SimpleNamespace(write_unknown_categories=lambda: None)

    monkeypatch.setattr(unpack_batch, "logger", fake_logger)
    monkeypatch.setattr(unpack_batch, "unpack_champion", _fake_unpack_champion)
    monkeypatch.setattr(unpack_batch, "unpack_map", _fail_unpack_map)

    unpack_batch.execute_tasks(
        [("champion", 1, "英雄ID 1"), ("map", 11, "地图ID 11")],
        reader,
        max_workers=1,
        ctx=ctx,
    )

    assert opt_calls == [{"exception": False}]
    assert any("地图ID 11 解包失败，将继续后续任务: map boom" in line for line in warnings)
    assert any("成功 1 个，失败 1 个" in line for line in warnings)
    assert successes == []
    assert errors == []


def test_execute_tasks_uses_warning_summary_for_partial_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ctx = _build_ctx(tmp_path)
    infos: list[str] = []
    warnings: list[str] = []
    successes: list[str] = []
    errors: list[str] = []
    opt_calls: list[dict[str, object]] = []

    def _record_warning(message: str) -> None:
        warnings.append(message)

    def _opt_logger(**kwargs):
        opt_calls.append(kwargs)
        return SimpleNamespace(warning=_record_warning)

    fake_logger = SimpleNamespace(
        info=infos.append,
        debug=lambda _message: None,
        success=successes.append,
        warning=warnings.append,
        error=errors.append,
        opt=_opt_logger,
    )

    def _fake_build_champion_mapping(*_args, **_kwargs) -> dict[str, object]:
        return {}

    def _fail_build_map_mapping(*_args, **_kwargs) -> dict[str, object]:
        raise RuntimeError("map boom")

    monkeypatch.setattr(mapping_batch, "logger", fake_logger)
    monkeypatch.setattr(mapping_session, "_create_wwiser_manager", lambda _ctx: None)
    monkeypatch.setattr(mapping_batch, "build_champion", _fake_build_champion_mapping)
    monkeypatch.setattr(mapping_batch, "build_map", _fail_build_map_mapping)

    m_mapping.execute_tasks(
        [("champion", 1, "英雄ID 1"), ("map", 11, "地图ID 11")],
        SimpleNamespace(),
        max_workers=1,
        ctx=ctx,
    )

    assert opt_calls == [{"exception": False}]
    assert any("地图ID 11 映射失败，将继续后续任务: map boom" in line for line in warnings)
    assert any("成功 1 个，失败 1 个" in line for line in warnings)
    assert successes == []
    assert errors == []


def test_get_cached_hirc_uses_native_hirc_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bnk_path = tmp_path / "events.bnk"
    hirc_cache_dir = tmp_path / "cache"
    native_hirc = object()
    captured: dict[str, object] = {}

    def fake_native_from_bnk(path: Path, *, cache_dir: Path) -> object:
        captured["native_args"] = (path, cache_dir)
        return native_hirc

    def fail_wwiser_from_bnk(*_args, **_kwargs) -> object:
        pytest.fail("默认路径不应调用 WwiserHIRC")

    monkeypatch.setattr(mapping_session, "NativeHIRC", SimpleNamespace(from_bnk=fake_native_from_bnk))
    monkeypatch.setattr(mapping_session, "WwiserHIRC", SimpleNamespace(from_bnk=fail_wwiser_from_bnk))

    result = mapping_session._get_cached_hirc(
        bnk_path=bnk_path,
        hirc_cache_dir=hirc_cache_dir,
        wwiser_manager=None,
        runtime_cache=None,
    )

    assert result is native_hirc
    assert captured["native_args"] == (bnk_path, hirc_cache_dir)


def test_get_cached_hirc_uses_wwiser_when_manager_is_provided(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bnk_path = tmp_path / "events.bnk"
    hirc_cache_dir = tmp_path / "cache"
    wwiser_manager = object()
    wwiser_hirc = object()
    captured: dict[str, object] = {}

    def fail_native_from_bnk(*_args, **_kwargs) -> object:
        pytest.fail("显式提供 wwiser_manager 时不应调用 NativeHIRC")

    def fake_wwiser_from_bnk(path: Path, *, cache_dir: Path, wwiser_manager: object) -> object:
        captured["wwiser_args"] = (path, cache_dir, wwiser_manager)
        return wwiser_hirc

    monkeypatch.setattr(mapping_session, "NativeHIRC", SimpleNamespace(from_bnk=fail_native_from_bnk))
    monkeypatch.setattr(mapping_session, "WwiserHIRC", SimpleNamespace(from_bnk=fake_wwiser_from_bnk))

    result = mapping_session._get_cached_hirc(
        bnk_path=bnk_path,
        hirc_cache_dir=hirc_cache_dir,
        wwiser_manager=wwiser_manager,
        runtime_cache=None,
    )

    assert result is wwiser_hirc
    assert captured["wwiser_args"] == (bnk_path, hirc_cache_dir, wwiser_manager)


def test_mapping_module_exposes_execute_tasks() -> None:
    """映射包应暴露新的批量入口。"""

    assert callable(m_mapping.execute_tasks)
