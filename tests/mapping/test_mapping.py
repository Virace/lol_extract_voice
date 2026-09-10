"""测试事件映射构建阶段的日志汇总行为。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from loguru import logger

import lol_audio_unpack.mapping.batch as mapping_batch
import lol_audio_unpack.mapping.entity as mapping_entity
import lol_audio_unpack.mapping.session as mapping_session
from lol_audio_unpack.app.path_layout import format_entity_folder_name, format_sub_entity_folder_name
from lol_audio_unpack.app.results import ResultStatus, StageResult
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


def _patch_batch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换批处理测试不需要的 HIRC 运行时依赖。"""
    monkeypatch.setattr(mapping_session, "_create_wwiser_manager", lambda _ctx: object())
    monkeypatch.setattr(
        mapping_session,
        "RuntimeCache",
        lambda cache_lock=None: SimpleNamespace(cache_lock=cache_lock),
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
    mapping_path = hash_dir / "champions" / "1-test-entity.msgpack"
    persisted: list[Path] = []
    monkeypatch.setattr(mapping_entity, "write_data", lambda *args, **kwargs: mapping_path)

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
            persisted_mapping_callback=persisted.append,
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
    assert persisted == [mapping_path]


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
    _patch_batch_runtime(monkeypatch)

    result = mapping_batch.execute_tasks(
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
    assert result.status is ResultStatus.SUCCESS
    assert result.entities[0].entity_id == 1
    assert result.entities[0].entity_name == "测试英雄"


def test_execute_tasks_single_worker_keeps_success_and_failure_results(monkeypatch) -> None:
    """单线程 batch 应继续处理并返回稳定的实体结果。"""
    failed_entity_id = 2

    def build_entity(_entity_type: str, entity_id: int | str, *_args, **_kwargs) -> None:
        if entity_id == failed_entity_id:
            raise RuntimeError("map mapping failed")

    monkeypatch.setattr(mapping_batch, "_build_entity", build_entity)
    _patch_batch_runtime(monkeypatch)

    result = mapping_batch.execute_tasks(
        [("champion", 1, "成功英雄"), ("map", 2, "失败地图")],
        _FakeReader(),
        max_workers=1,
        ctx=_build_fake_ctx(),
    )

    assert result.status is ResultStatus.PARTIAL
    assert [(entity.entity_type, entity.entity_id, entity.entity_name) for entity in result.entities] == [
        ("champion", 1, "成功英雄"),
        ("map", 2, "失败地图"),
    ]
    assert [entity.status for entity in result.entities] == [ResultStatus.SUCCESS, ResultStatus.FAILED]
    assert result.entities[1].error_type == "RuntimeError"
    assert result.entities[1].error_message == "map mapping failed"


def test_execute_tasks_preserves_mapping_artifacts_for_success_and_late_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """mapping batch 应按输入顺序保留真实落盘路径，且不伪造空输出。"""
    failed_entity_id = 2
    empty_entity_id = 3

    def build_entity(_entity_type: str, entity_id: int | str, *_args, **kwargs) -> None:
        callback = kwargs["persisted_mapping_callback"]
        if entity_id != empty_entity_id:
            path = tmp_path / f"{entity_id}.msgpack"
            path.write_bytes(b"mapping")
            callback(path)
        if entity_id == failed_entity_id:
            raise OSError("write completed but summary failed")

    monkeypatch.setattr(mapping_batch, "_build_entity", build_entity)
    _patch_batch_runtime(monkeypatch)

    result = mapping_batch.execute_tasks(
        [
            ("champion", 1, "成功英雄"),
            ("map", failed_entity_id, "落盘后失败地图"),
            ("champion", empty_entity_id, "空映射英雄"),
        ],
        _FakeReader(),
        max_workers=3,
        ctx=_build_fake_ctx(),
    )

    assert [entity.entity_id for entity in result.entities] == [1, 2, 3]
    assert [entity.status for entity in result.entities] == [
        ResultStatus.SUCCESS,
        ResultStatus.FAILED,
        ResultStatus.SUCCESS,
    ]
    assert [entity.artifacts for entity in result.entities] == [
        (str(tmp_path / "1.msgpack"),),
        (str(tmp_path / "2.msgpack"),),
        (),
    ]


def test_mapping_write_helpers_return_actual_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mapping 与 integrated 写入 helper 应返回实际落盘路径。"""
    entity_data = SimpleNamespace(entity_type="champion", entity_id=1, entity_name="测试英雄")
    ctx = _build_fake_ctx(hash_path=tmp_path / "hashes")
    mapping_path = tmp_path / "hashes" / "champions" / "1.msgpack"
    integrated_path = tmp_path / "hashes" / "integrated" / "champions" / "1.msgpack"
    written_paths = iter((mapping_path, integrated_path))
    monkeypatch.setattr(mapping_entity, "write_data", lambda *_args, **_kwargs: next(written_paths))

    mapping_result = {"metadata": {}, "skins": {"1001": {"events": {"VO": {"evt": [1]}}}}}
    integrated_result = {"data": {"skins": [{"id": 1001}]}}

    assert (
        mapping_entity._write_mapping_result(
            mapping_result,
            "skins",
            tmp_path / "hashes" / "champions",
            entity_data,
            ctx=ctx,
        )
        == mapping_path
    )
    assert (
        mapping_entity._write_integrated_result(entity_data, integrated_result, tmp_path / "hashes", ctx=ctx)
        == integrated_path
    )


def test_execute_tasks_multi_worker_keeps_input_results_and_completion_progress(monkeypatch) -> None:
    """多线程结果应保持输入顺序，而进度应保持实际完成顺序。"""
    fast_entity_id = 2
    started = Event()
    release_slow_task = Event()
    progress_events: list[tuple[str, int, int, str]] = []

    def build_entity(_entity_type: str, entity_id: int | str, *_args, **_kwargs) -> None:
        if entity_id == 1:
            started.set()
            assert release_slow_task.wait(timeout=2)
            return
        assert entity_id == fast_entity_id
        assert started.wait(timeout=2)
        raise RuntimeError("fast mapping failed")

    def record_progress(entity_type: str, current: int, total: int, message: str) -> None:
        progress_events.append((entity_type, current, total, message))
        if message == "快速失败 映射失败":
            release_slow_task.set()

    monkeypatch.setattr(mapping_batch, "_build_entity", build_entity)
    _patch_batch_runtime(monkeypatch)

    result = mapping_batch.execute_tasks(
        [("champion", 1, "缓慢成功"), ("map", fast_entity_id, "快速失败")],
        _FakeReader(),
        max_workers=2,
        ctx=_build_fake_ctx(),
        progress_callback=record_progress,
    )

    completed_messages = [message for *_details, message in progress_events if not message.startswith("正在处理:")]
    assert completed_messages == ["快速失败 映射失败", "缓慢成功 映射完成"]
    assert [entity.entity_id for entity in result.entities] == [1, 2]
    assert [entity.status for entity in result.entities] == [ResultStatus.SUCCESS, ResultStatus.FAILED]
    assert result.status is ResultStatus.PARTIAL


def test_execute_tasks_returns_failed_stage_when_all_entities_fail(monkeypatch) -> None:
    """全部实体失败时 stage 不得被错误聚合为成功。"""

    def build_entity(*_args, **_kwargs) -> None:
        raise RuntimeError("mapping failed")

    monkeypatch.setattr(
        mapping_batch,
        "_build_entity",
        build_entity,
    )
    _patch_batch_runtime(monkeypatch)

    result = mapping_batch.execute_tasks(
        [("champion", 1, "英雄一"), ("map", 2, "地图二")],
        _FakeReader(),
        max_workers=1,
        ctx=_build_fake_ctx(),
    )

    assert result.status is ResultStatus.FAILED
    assert result.failed_count == len(result.entities)
    assert [entity.entity_id for entity in result.entities] == [1, 2]


def test_execute_tasks_returns_successful_no_op_for_empty_tasks() -> None:
    """空任务集是合法 no-op，应返回成功的 mapping stage。"""
    result = mapping_batch.execute_tasks([], _FakeReader(), ctx=_build_fake_ctx())

    assert isinstance(result, StageResult)
    assert result.status is ResultStatus.SUCCESS
    assert result.entities == ()
    assert result.note == "没有任何任务需要执行"


def test_execute_tasks_rejects_unknown_type_before_creating_runtime(monkeypatch) -> None:
    """未知实体类型属于 stage 输入错误，不得降级为单项 partial。"""
    monkeypatch.setattr(
        mapping_session,
        "_create_wwiser_manager",
        lambda _ctx: pytest.fail("未知实体类型不应初始化 mapping 运行时"),
    )

    with pytest.raises(ValueError, match="未知的实体类型: unknown"):
        mapping_batch.execute_tasks(
            [("unknown", 1, "未知实体")],
            _FakeReader(),
            ctx=_build_fake_ctx(),
        )


def test_execute_tasks_reraises_keyboard_interrupt(monkeypatch) -> None:
    """中断信号不属于可继续的实体失败，必须向调用边界上抛。"""

    def build_entity(*_args, **_kwargs) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        mapping_batch,
        "_build_entity",
        build_entity,
    )
    _patch_batch_runtime(monkeypatch)

    with pytest.raises(KeyboardInterrupt):
        mapping_batch.execute_tasks(
            [("champion", 1, "被中断英雄")],
            _FakeReader(),
            max_workers=1,
            ctx=_build_fake_ctx(),
        )


def test_mapping_builders_return_stage_result_for_empty_tasks(monkeypatch) -> None:
    """所有公开 mapping builder 均应在合法 no-op 时返回 stage 结果。"""
    monkeypatch.setattr(mapping_batch, "generate_champion_tasks", lambda *_args: [])
    monkeypatch.setattr(mapping_batch, "generate_map_tasks", lambda *_args: [])
    reader = _FakeReader()
    ctx = _build_fake_ctx()

    results = (
        mapping_batch.build_all(reader, include_champions=False, include_maps=False, ctx=ctx),
        mapping_batch.build_champions(reader, [1], ctx=ctx),
        mapping_batch.build_maps(reader, [1], ctx=ctx),
        mapping_batch.build_resource_packs(reader, [], ctx=ctx),
    )

    assert all(isinstance(result, StageResult) for result in results)
    assert all(result.status is ResultStatus.SUCCESS for result in results)
    assert all(result.entities == () for result in results)


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


@pytest.mark.parametrize("source", ["missing", "shared", "different_wad", "different_entry", "unresolved"])
def test_local_mapping_without_events_writes_partial_diagnostics(tmp_path: Path, monkeypatch, source: str) -> None:
    """仅同一物理 Base bank 可继承事件；缺失、冲突与不同资源仍不完整。"""
    binding = BankBinding(
        category="Test_Base_VO",
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
    if source != "missing":
        base = replace(binding, sub_entity="1000")
        if source == "different_wad":
            binding = replace(binding, wad="Game/other.wad.client")
        elif source == "different_entry":
            binding = replace(binding, entry_hash="0000000000000002")
        elif source == "unresolved":
            binding = replace(binding, status=BindingStatus.MISSING)
        entity_data.resource_banks = (
            AudioBank(sub_id="1000", audio_type="VO", binding=base),
            AudioBank(sub_id="1001", audio_type="VO", binding=binding),
        )
        entity_data.events = {"1000": {"events": {"Test_Base_VO": ["evt"]}}}
        monkeypatch.setattr(
            mapping_entity,
            "_build_bound_category_mapping",
            lambda *_args, **_kwargs: (_FakeAudioMapping({"evt": [101]}), None),
        )
    written: list[dict] = []
    monkeypatch.setattr(mapping_entity, "write_data", lambda data, *_args, **_kwargs: written.append(data))

    result = build_entity(
        entity_data, _FakeReader(), ctx=_build_fake_ctx(cache_path=tmp_path / "cache", hash_path=tmp_path / "hashes")
    )

    if source == "shared":
        assert result["skins"]["1001"]["events"] == {"Test_Base_VO": {"evt": [101]}}
        assert result["mappingDiagnostics"]["completeness"] == "complete"
        assert result["mappingDiagnostics"]["missingEventCategories"] == []
    else:
        assert "1001" not in result["skins"]
        assert result["mappingDiagnostics"]["completeness"] == "partial"
        if source != "unresolved":
            assert result["mappingDiagnostics"]["missingEventCategories"] == [
                {"subEntity": "1001", "category": "Test_Base_VO"}
            ]
    assert written == [result]

    if source == "shared":
        reader = SimpleNamespace(
            get_champion=lambda _id: {
                "id": 1,
                "skins": [{"id": 1000, "chromas": [{"id": 1001, "chromaNames": {"zh_CN": "炫彩"}}]}],
            },
            get_champion_banks=lambda _id: {"skins": {}, "skinAudio": {"1001": {"VO": "shared", "SFX": "absent"}}},
        )
        integrated = mapping_entity.integrate_entity(entity_data, reader, result)
        assert [skin["id"] for skin in integrated["data"]["skins"]] == [1000, 1001]
        assert integrated["data"]["skins"][1]["skinNames"] == {"zh_CN": "炫彩"}
        assert integrated["data"]["skins"][1]["events"]["Test_Base_VO"]["mapping"] == {"evt": [101]}
        assert integrated["data"]["skinAudio"]["1001"]["VO"] == "shared"


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


def test_extract_bnk_does_not_block_unrelated_banks() -> None:
    """一个 bank 等待磁盘时，不同 bank 仍可完成提取，失败项允许重试。"""
    started = Event()
    release = Event()
    cache = mapping_session.RuntimeCache(cache_lock=Lock())
    key = ("Game/first.wad.client", "first.bnk")

    def blocked() -> None:
        """保持首个提取在临界区中，直到独立提取完成。"""
        started.set()
        assert release.wait(timeout=3)
        raise OSError("暂时不可读")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(mapping_session._extract_bnk_once, key, blocked, cache)
        assert started.wait(timeout=2)
        second = executor.submit(
            mapping_session._extract_bnk_once, ("Game/second.wad.client", "second.bnk"), lambda: None, cache
        )
        try:
            assert second.result(timeout=2) is True
        finally:
            release.set()
        with pytest.raises(OSError, match="暂时不可读"):
            first.result(timeout=2)
    assert mapping_session._extract_bnk_once(key, lambda: None, cache) is True


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
    integrated_path = tmp_path / "hashes" / "integrated" / "champions" / "1.msgpack"
    persisted: list[Path] = []
    monkeypatch.setattr(
        mapping_entity,
        "write_data",
        lambda data, *_args, **_kwargs: (written.append(data), integrated_path)[1],
    )

    result = build_entity(
        entity_data,
        reader,
        integrate_data=True,
        ctx=_build_fake_ctx(cache_path=tmp_path / "cache", hash_path=tmp_path / "hashes"),
        persisted_mapping_callback=persisted.append,
    )

    assert result["mappingDiagnostics"]["completeness"] == "failed"
    assert result["mappingDiagnostics"]["unresolvedBankCategories"] == [
        {"subEntity": "1001", "category": "CHARACTER_VO", "status": "missing"}
    ]
    assert written == [result]
    assert persisted == [integrated_path]


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
