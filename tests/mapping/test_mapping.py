"""测试事件映射构建阶段的日志汇总行为。"""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

from loguru import logger

import lol_audio_unpack.mapping.batch as mapping_batch
import lol_audio_unpack.mapping.entity as mapping_entity
import lol_audio_unpack.mapping.session as mapping_session
from lol_audio_unpack.app.path_layout import format_entity_folder_name, format_sub_entity_folder_name
from lol_audio_unpack.app.types import AppConfig, AppContext, AppPaths
from lol_audio_unpack.mapping import build_entity
from lol_audio_unpack.model import AudioBank, AudioEntityData
from lol_audio_unpack.model.binding import BankBinding, BindingDiagnostics, BindingRole, BindingStatus, Completeness

FAKE_GAME_PATH = Path("FakeGame")
FAKE_OUTPUT_PATH = Path("FakeOut")


class _FakeReader:
    """提供 `build_entity` 所需最小读取接口。"""

    version = "test-version"

    @staticmethod
    def get_languages() -> list[str]:
        """返回测试使用的语言列表。"""
        return ["zh_CN"]


class _FakeWad:
    """将请求提取的 bnk 文件写入缓存目录。"""

    @staticmethod
    def extract(bnk_paths: list[str], out_dir: Path) -> None:
        """模拟 WAD 提取行为。"""
        for bnk_rel_path in bnk_paths:
            target = Path(out_dir) / bnk_rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fake-bnk")


class _FakeAudioMapping:
    """提供测试所需的最小映射对象。"""

    def __init__(self, forward_mapping: dict[str, list[int]]) -> None:
        self.forward_mapping = forward_mapping

    def merge_with(self, other: "_FakeAudioMapping") -> None:
        """合并其他映射结果。"""
        for event_name, sound_ids in other.forward_mapping.items():
            merged_ids = self.forward_mapping.setdefault(event_name, [])
            merged_ids.extend(sound_ids)
            self.forward_mapping[event_name] = sorted(set(merged_ids))


class _FakeAudioEventMapper:
    """根据测试事件列表返回固定映射结果。"""

    def __init__(self, event_list: list[str], _hirc: object) -> None:
        self._event_list = tuple(event_list)

    def build_mapping(self) -> _FakeAudioMapping:
        """返回固定映射结果，模拟部分事件未映射。"""
        if self._event_list == ("evt_ok", "evt_skip"):
            return _FakeAudioMapping({"evt_ok": [101]})
        return _FakeAudioMapping({})


def _build_fake_ctx(
    *,
    game_path: Path | None = None,
    cache_path: Path | None = None,
    hash_path: Path | None = None,
) -> AppContext:
    """创建最小运行上下文。"""
    game_path = game_path or FAKE_GAME_PATH
    output_path = cache_path.parent if cache_path is not None else FAKE_OUTPUT_PATH
    cache_path = cache_path or output_path / "cache"
    hash_path = hash_path or output_path / "hashes"
    return AppContext(
        config=AppConfig(
            game_path=game_path,
            output_path=output_path,
            dev_mode=False,
        ),
        paths=AppPaths(
            audio_path=output_path / "audios",
            wav_path=output_path / "wavs",
            temp_path=output_path / "temps",
            log_path=output_path / "logs",
            cache_path=cache_path,
            hash_path=hash_path,
            report_path=output_path / "reports",
            manifest_path=output_path / "manifest",
            local_version_file=output_path / "game_version",
            game_champion_path=game_path / "Game" / "DATA" / "FINAL" / "Champions",
            game_maps_path=game_path / "Game" / "DATA" / "FINAL" / "Maps" / "Shipping",
            game_lcu_path=game_path / "LeagueClient" / "Plugins" / "rcp-be-lol-game-data",
        ),
    )


def test_build_entity_uses_single_success_summary(monkeypatch, tmp_path: Path) -> None:
    """类别级完成日志应降为 debug，实体级只保留一条统计 success。"""
    cache_dir = tmp_path / "cache"
    hash_dir = tmp_path / "hashes"
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "root.wad.client").write_bytes(b"fake-wad")

    monkeypatch.setattr(mapping_session, "_get_wad", lambda _wad_path, runtime_cache=None: _FakeWad())
    monkeypatch.setattr(mapping_entity, "AudioEventMapper", _FakeAudioEventMapper)
    monkeypatch.setattr(mapping_entity, "write_data", lambda *args, **kwargs: None)

    def fake_get_cached_hirc(*, bnk_path: Path, **_kwargs) -> object:
        if bnk_path.name == "bad_events.bnk":
            raise RuntimeError("读取 MusicSwitch.rule_destination_count 失败")
        return object()

    monkeypatch.setattr(mapping_session, "_get_cached_hirc", fake_get_cached_hirc)

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={
            "1001": {
                "name": "Test Skin",
                "categories": {
                    "CAT_OK": [["ok_events.bnk"]],
                    "CAT_ERR": [["bad_events.bnk"]],
                },
            }
        },
        wad_root="root.wad.client",
        wad_language=None,
        events={
            "1001": {
                "events": {
                    "CAT_OK": ["evt_ok", "evt_skip"],
                    "CAT_ERR": ["evt_problem"],
                }
            }
        },
    )

    log_lines: list[str] = []
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(
        lambda message: log_lines.append(str(message).rstrip()),
        format="{level}|{message}",
    )

    try:
        build_entity(
            entity_data=entity_data,
            reader=_FakeReader(),
            wwiser_manager=None,
            integrate_data=False,
            runtime_cache=None,
            ctx=_build_fake_ctx(game_path=game_dir, cache_path=cache_dir, hash_path=hash_dir),
        )
    finally:
        logger.remove(sink_id)

    assert any("DEBUG|完成 CAT_OK 的映射" in line for line in log_lines)
    assert not any("SUCCESS|完成 CAT_OK 的映射" in line for line in log_lines)
    assert any(
        "WARNING|处理路径组合 1 时出错: 读取 MusicSwitch.rule_destination_count 失败" in line for line in log_lines
    )

    warning_lines = [line for line in log_lines if "WARNING|" in line]
    assert any("Test Entity 的事件映射统计" in line for line in warning_lines)
    assert any("成功映射事件 1 个" in line for line in warning_lines)
    assert any("异常事件 1 个" in line for line in warning_lines)
    assert any("未映射跳过 1 个" in line for line in warning_lines)
    assert not any("SUCCESS|Test Entity 的事件映射统计" in line for line in log_lines)


def test_resolve_wad_path_uses_language_wad_for_vo_and_root_wad_for_other_categories(tmp_path: Path) -> None:
    """mapping 侧当前 WAD 解析应区分 VO 与非 VO 类别。"""
    game_dir = tmp_path / "game"
    language_wad = game_dir / "lang.wad.client"
    root_wad = game_dir / "root.wad.client"
    language_wad.parent.mkdir(parents=True, exist_ok=True)
    language_wad.write_bytes(b"lang")
    root_wad.write_bytes(b"root")

    ctx = _build_fake_ctx(
        game_path=game_dir,
        cache_path=tmp_path / "cache",
        hash_path=tmp_path / "hashes",
    )
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={},
        wad_root="root.wad.client",
        wad_language="lang.wad.client",
    )

    assert mapping_entity._resolve_wad_path(entity_data, "CHARACTER_VO", ctx=ctx) == language_wad
    assert mapping_entity._resolve_wad_path(entity_data, "CHARACTER_SFX", ctx=ctx) == root_wad

    language_wad.unlink()

    assert mapping_entity._resolve_wad_path(entity_data, "CHARACTER_VO", ctx=ctx) is None


def test_execute_tasks_emits_running_entity_progress_before_completion(monkeypatch) -> None:
    """mapping 批处理应先发出当前实体的运行中进度。"""
    progress_events: list[tuple[str, int, int, str]] = []

    monkeypatch.setattr(
        mapping_batch,
        "_build_entity",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        mapping_session,
        "_create_wwiser_manager",
        lambda _ctx: object(),
    )
    monkeypatch.setattr(
        mapping_session,
        "RuntimeCache",
        lambda cache_lock=None: SimpleNamespace(cache_lock=cache_lock),
    )

    mapping_batch.execute_tasks(
        [("champion", 1, "测试英雄")],
        _FakeReader(),
        max_workers=1,
        integrate_data=False,
        ctx=_build_fake_ctx(),
        progress_callback=lambda entity_type, current, total, message: progress_events.append(
            (entity_type, current, total, message)
        ),
    )

    assert progress_events == [
        ("champion", 0, 1, "正在处理: 测试英雄"),
        ("champion", 1, 1, "测试英雄 映射完成"),
    ]


def test_local_mapping_uses_binding_wad_namespace_and_path_level_audio_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """同名 events BNK 位于不同 WAD 时应分别映射并保留两个实际 WEM 路径。"""
    version = _FakeReader.version
    game_dir = tmp_path / "game"
    cache_dir = tmp_path / "cache"
    hash_dir = tmp_path / "hashes"
    for name in ("alpha.wad.client", "beta.wad.client"):
        target = game_dir / "Game" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(name.encode())
    ctx = _build_fake_ctx(game_path=game_dir, cache_path=cache_dir, hash_path=hash_dir)
    entity_folder = format_entity_folder_name("1", "test-entity", "Test Entity", "测试实体")
    skin_folder = format_sub_entity_folder_name("1001", "Test Skin")
    audio_dir = ctx.paths.audio_path / version / "champions" / entity_folder / skin_folder / "VO"
    audio_dir.mkdir(parents=True)
    (audio_dir / "101.wem").write_bytes(b"one")
    (audio_dir / "102.wem").write_bytes(b"two")

    bindings = tuple(
        BankBinding(
            category="CHARACTER_VO",
            path="assets/shared_events.bnk",
            normalized_path="",
            kind="BNK",
            wad=f"Game/{name}",
            entry_hash=entry_hash,
            source_bin=f"data/{name}.bin",
            role=BindingRole.LOCALIZED,
            status=BindingStatus.RESOLVED,
            sub_entity="1001",
        )
        for name, entry_hash in (("alpha.wad.client", "0000000000000001"), ("beta.wad.client", "0000000000000002"))
    )
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={"1001": {"name": "Test Skin", "categories": {}}},
        wad_root="Game/root.wad.client",
        events={"1001": {"events": {"CHARACTER_VO": ["evt"]}}},
        resource_banks=tuple(AudioBank(sub_id="1001", audio_type="VO", binding=binding) for binding in bindings),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )
    extracted: list[tuple[str, Path]] = []
    hirc_paths: list[Path] = []

    class _BoundWad:
        def __init__(self, path: Path) -> None:
            self.path = path

        def extract(self, paths: list[str], raw: bool = True) -> list[bytes]:
            assert raw is True
            extracted.append((self.path.name, Path(paths[0])))
            payload = b"alpha" if self.path.name.startswith("alpha") else b"beta"
            return [payload for _path in paths]

    class _BoundMapper:
        def __init__(self, _events: list[str], hirc: bytes) -> None:
            self.hirc = hirc

        def build_mapping(self) -> _FakeAudioMapping:
            return _FakeAudioMapping({"evt": [101 if self.hirc == b"alpha" else 102]})

    def fake_hirc(*, bnk_path: Path, **_kwargs) -> bytes:
        hirc_paths.append(bnk_path)
        return bnk_path.read_bytes()

    monkeypatch.setattr(mapping_session, "_get_wad", lambda path, runtime_cache=None: _BoundWad(path))
    monkeypatch.setattr(mapping_session, "_get_cached_hirc", fake_hirc)
    monkeypatch.setattr(mapping_entity, "AudioEventMapper", _BoundMapper)
    monkeypatch.setattr(mapping_entity, "write_data", lambda *args, **kwargs: None)

    result = build_entity(entity_data, _FakeReader(), runtime_cache=mapping_session.RuntimeCache(), ctx=ctx)

    assert result["skins"]["1001"]["events"]["CHARACTER_VO"] == {"evt": [101, 102]}
    assert result["skins"]["1001"]["audioPaths"]["CHARACTER_VO"]["evt"] == [
        f"{skin_folder}/VO/101.wem",
        f"{skin_folder}/VO/102.wem",
    ]
    assert result["mappingDiagnostics"]["completeness"] == "complete"
    assert result["mappingDiagnostics"]["mappedWemCount"] == len(bindings)
    namespaces = {path.parents[1].name for path in hirc_paths}
    assert namespaces == {
        sha256(b"Game/alpha.wad.client").hexdigest(),
        sha256(b"Game/beta.wad.client").hexdigest(),
    }
    assert {item[0] for item in extracted} == {"alpha.wad.client", "beta.wad.client"}


def test_local_mapping_without_events_writes_partial_diagnostics(tmp_path: Path, monkeypatch) -> None:
    """local 有效 bank 但无 events 时应可返回诊断，不伪造映射。"""
    binding = BankBinding(
        category="CHARACTER_VO",
        path="assets/voice_events.bnk",
        normalized_path="",
        kind="BNK",
        wad="Game/voice.wad.client",
        entry_hash="0000000000000001",
        source_bin="data/voice.bin",
        role=BindingRole.LOCALIZED,
        status=BindingStatus.RESOLVED,
        sub_entity="1001",
    )
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={"1001": {"name": "Test Skin", "categories": {}}},
        wad_root="Game/root.wad.client",
        events={},
        resource_banks=(AudioBank(sub_id="1001", audio_type="VO", binding=binding),),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )
    written: list[dict] = []
    monkeypatch.setattr(mapping_entity, "write_data", lambda data, *_args, **_kwargs: written.append(data))

    result = build_entity(
        entity_data, _FakeReader(), ctx=_build_fake_ctx(cache_path=tmp_path / "cache", hash_path=tmp_path / "hashes")
    )

    assert result["skins"] == {}
    assert result["mappingDiagnostics"]["completeness"] == "partial"
    assert result["mappingDiagnostics"]["missingEventCategories"] == [{"subEntity": "1001", "category": "CHARACTER_VO"}]
    assert written == [result]


def test_local_mapping_reports_events_only_category_as_missing_bank(tmp_path: Path, monkeypatch) -> None:
    """events-only 分类必须进入 unresolved bank 诊断。"""
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={"1001": {"name": "Test Skin", "categories": {}}},
        wad_root="Game/root.wad.client",
        events={"1001": {"events": {"CHARACTER_VO": ["evt"]}}},
        resource_banks=(),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )
    monkeypatch.setattr(mapping_entity, "write_data", lambda *_args, **_kwargs: None)

    result = build_entity(
        entity_data,
        _FakeReader(),
        ctx=_build_fake_ctx(cache_path=tmp_path / "cache", hash_path=tmp_path / "hashes"),
    )

    assert result["mappingDiagnostics"]["completeness"] == "partial"
    assert result["mappingDiagnostics"]["unresolvedBankCategories"] == [
        {"subEntity": "1001", "category": "CHARACTER_VO", "status": "missing"}
    ]


def test_local_mapping_rejects_bank_path_that_escapes_cache_root(tmp_path: Path, monkeypatch) -> None:
    """异常 binding path 不得把 BNK 写到 WAD namespace 外。"""
    game_dir = tmp_path / "game"
    wad_path = game_dir / "Game" / "voice.wad.client"
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"wad")
    binding = BankBinding(
        category="CHARACTER_VO",
        path="../escape_events.bnk",
        normalized_path="",
        kind="BNK",
        wad="Game/voice.wad.client",
        entry_hash="0000000000000001",
        source_bin="data/voice.bin",
        role=BindingRole.LOCALIZED,
        status=BindingStatus.RESOLVED,
        sub_entity="1001",
    )
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={"1001": {"name": "Test Skin", "categories": {}}},
        wad_root="Game/root.wad.client",
        events={"1001": {"events": {"CHARACTER_VO": ["evt"]}}},
        resource_banks=(AudioBank(sub_id="1001", audio_type="VO", binding=binding),),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )
    monkeypatch.setattr(mapping_session, "_get_wad", lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(mapping_entity, "write_data", lambda *_args, **_kwargs: None)
    ctx = _build_fake_ctx(
        game_path=game_dir,
        cache_path=tmp_path / "cache",
        hash_path=tmp_path / "hashes",
    )

    result = build_entity(entity_data, _FakeReader(), ctx=ctx)

    assert result["mappingDiagnostics"]["completeness"] == "failed"
    assert result["mappingDiagnostics"]["errorCategories"] == [{"subEntity": "1001", "category": "CHARACTER_VO"}]
    assert not (ctx.paths.cache_path / _FakeReader.version / "banks" / "escape_events.bnk").exists()


def test_extract_bnk_once_is_atomic_for_concurrent_same_key() -> None:
    """并发实体共享相同 binding 时只能执行一次磁盘提取。"""
    started = Event()
    release = Event()
    calls: list[str] = []
    runtime_cache = mapping_session.RuntimeCache(cache_lock=Lock())

    def extract() -> None:
        calls.append("extract")
        started.set()
        assert release.wait(timeout=2)

    key = ("Game/shared.wad.client", "assets/shared_events.bnk")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(mapping_session._extract_bnk_once, key, extract, runtime_cache)
        assert started.wait(timeout=2)
        second = executor.submit(mapping_session._extract_bnk_once, key, extract, runtime_cache)
        release.set()

    assert first.result() is True
    assert second.result() is False
    assert calls == ["extract"]


def test_integrated_local_mapping_keeps_failed_diagnostics_without_legacy_banks(tmp_path: Path, monkeypatch) -> None:
    """全量 binding 未解析时，integrated 输出仍应保存 failed 诊断。"""
    binding = BankBinding(
        category="CHARACTER_VO",
        path="assets/missing_events.bnk",
        normalized_path="",
        kind="BNK",
        wad=None,
        entry_hash="0000000000000001",
        source_bin="data/missing.bin",
        role=None,
        status=BindingStatus.MISSING,
        sub_entity="1001",
    )
    diagnostics = BindingDiagnostics(
        completeness=Completeness.FAILED,
        unresolved_banks=({"category": "CHARACTER_VO", "path": binding.path, "status": "missing"},),
    )
    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={"1001": {"name": "Test Skin", "categories": {}}},
        wad_root="Game/root.wad.client",
        events={},
        resource_banks=(AudioBank(sub_id="1001", audio_type="VO", binding=binding),),
        binding_diagnostics=diagnostics,
    )
    reader = SimpleNamespace(
        version="test-version",
        get_languages=lambda: ["zh_CN"],
        get_champion=lambda _id: {
            "id": 1,
            "names": {"zh_CN": "测试实体"},
            "skins": [{"id": 1001, "skinNames": {"zh_CN": "Test Skin"}}],
        },
        get_champion_banks=lambda _id: {},
    )
    written: list[dict] = []
    monkeypatch.setattr(mapping_entity, "write_data", lambda data, *_args, **_kwargs: written.append(data))

    result = build_entity(
        entity_data,
        reader,
        integrate_data=True,
        ctx=_build_fake_ctx(cache_path=tmp_path / "cache", hash_path=tmp_path / "hashes"),
    )

    assert result["mappingDiagnostics"]["completeness"] == "failed"
    assert result["mappingDiagnostics"]["unresolvedBankCategories"] == [
        {"subEntity": "1001", "category": "CHARACTER_VO", "status": "missing"}
    ]
    assert written == [result]


def test_hirc_memory_cache_key_includes_wad_identity_and_backend(tmp_path: Path, monkeypatch) -> None:
    """同名 BNK 的 HIRC 缓存不能仅靠临时绝对路径偶然区分。"""
    alpha = tmp_path / "alpha" / "shared_events.bnk"
    beta = tmp_path / "beta" / "shared_events.bnk"
    alpha.parent.mkdir(parents=True)
    beta.parent.mkdir(parents=True)
    alpha.write_bytes(b"alpha")
    beta.write_bytes(b"beta")
    parsed: list[Path] = []

    class _FakeNativeHirc:
        @staticmethod
        def from_bnk(path: Path, cache_dir: Path) -> object:  # noqa: ARG004
            parsed.append(path)
            return object()

    monkeypatch.setattr(mapping_session, "NativeHIRC", _FakeNativeHirc)
    cache = mapping_session.RuntimeCache()
    hirc_dir = tmp_path / "hirc"

    first = mapping_session._get_cached_hirc(
        alpha,
        hirc_dir,
        None,
        cache,
        wad_identity="Game/alpha.wad.client",
        normalized_bank_path="assets/shared_events.bnk",
    )
    again = mapping_session._get_cached_hirc(
        alpha,
        hirc_dir,
        None,
        cache,
        wad_identity="Game/alpha.wad.client",
        normalized_bank_path="assets/shared_events.bnk",
    )
    second = mapping_session._get_cached_hirc(
        beta,
        hirc_dir,
        None,
        cache,
        wad_identity="Game/beta.wad.client",
        normalized_bank_path="assets/shared_events.bnk",
    )

    assert first is again
    assert first is not second
    assert parsed == [alpha, beta]
    assert set(cache.hirc_cache) == {
        ("Game/alpha.wad.client", "assets/shared_events.bnk", "native"),
        ("Game/beta.wad.client", "assets/shared_events.bnk", "native"),
    }
