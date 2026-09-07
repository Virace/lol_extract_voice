"""resource-pack 解包消费者的定向测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from lol_audio_unpack.app.path_layout import format_entity_folder_name, get_entity_path_component
from lol_audio_unpack.app.resource_pack import build_resource_pack_key
from lol_audio_unpack.app.results import ResultStatus
from lol_audio_unpack.model import AudioBank, AudioEntityData
from lol_audio_unpack.model.binding import BankBinding, BindingDiagnostics, BindingRole, BindingStatus, Completeness
from lol_audio_unpack.unpack import batch as unpack_batch
from lol_audio_unpack.unpack import entity as unpack_entity
from lol_audio_unpack.unpack.stats import StageResult as UnpackStageResult


class _FakeWad:
    """返回一个可供 BNK 边界解析的固定容器。"""

    @staticmethod
    def extract(_paths, *, raw: bool):  # noqa: ANN001
        """返回单个固定容器数据。"""
        assert raw is True
        return [b"bank"]


class _FakeWem:
    """模拟一个可持久化的 WEM 条目。"""

    id = 101
    data = b"wem"

    @staticmethod
    def save_file(path: Path) -> None:
        """写入固定 WEM 字节。"""
        path.write_bytes(b"wem")


class _FakeBnk:
    """模拟 BNK 容器的单 WEM 提取。"""

    def __init__(self, raw_data: bytes) -> None:
        """验证解包输入保持原始容器字节。"""
        assert raw_data == b"bank"

    @staticmethod
    def extract_files() -> list[_FakeWem]:
        """返回固定 WEM。"""
        return [_FakeWem()]


def _build_entity(key: str) -> AudioEntityData:
    """创建使用单个 resolved binding 的 resource-pack 实体。"""
    binding = BankBinding(
        category="MODE_TFT_NPC_ElderDragon_SFX",
        path="assets/elder_dragon_audio.bnk",
        normalized_path="assets/elder_dragon_audio.bnk",
        kind="BNK",
        wad="Game/DATA/FINAL/TFTCommon.wad.client",
        entry_hash="0000000000000001",
        source_bin="resource_pack/0000000000000002.bin",
        role=BindingRole.ROOT,
        status=BindingStatus.RESOLVED,
    )
    return AudioEntityData(
        entity_id=key,
        entity_name="MODE TFT NPC ElderDragon SFX",
        entity_alias="mode_tft_npc_elderdragon_sfx",
        entity_title=None,
        entity_type="resource_pack",
        sub_entities={key: {"name": "MODE TFT NPC ElderDragon SFX", "categories": {}}},
        wad_root="Game/DATA/FINAL/TFTCommon.wad.client",
        resource_banks=(AudioBank(sub_id=key, audio_type="SFX", binding=binding),),
        binding_diagnostics=BindingDiagnostics(completeness=Completeness.COMPLETE),
    )


@pytest.mark.parametrize("container", ["audio", "metadata", "corrupt", "empty", "empty_wpk"])
def test_bound_resource_pack_extracts_to_isolated_safe_output_and_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    container: str,
) -> None:
    """合法无音频 BNK 可正常跳过，空字节、损坏与空 WPK 仍失败并保留原因。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    game_path = tmp_path / "game"
    source_wad = game_path / "Game" / "DATA" / "FINAL" / "TFTCommon.wad.client"
    source_wad.parent.mkdir(parents=True)
    source_wad.write_bytes(b"wad")
    ctx = SimpleNamespace(
        game_path=game_path,
        audio_path=tmp_path / "audios",
        report_path=tmp_path / "reports",
        game_region="zh_CN",
        include_types=("SFX",),
        exclude_types=(),
        group_by_type=True,
        config=SimpleNamespace(dev_mode=False),
    )
    reader = SimpleNamespace(version="16.16")
    monkeypatch.setattr(unpack_entity, "_get_wad_instance", lambda *_args, **_kwargs: _FakeWad())
    monkeypatch.setattr(unpack_entity, "BNK", _FakeBnk)
    if container == "metadata":
        monkeypatch.setattr(_FakeBnk, "extract_files", staticmethod(lambda: []))
    elif container == "corrupt":

        def fail_parse(_raw):
            """模拟外部解析器拒绝损坏内容。"""
            raise ValueError("损坏的 BNK")

        monkeypatch.setattr(unpack_entity, "BNK", fail_parse)
    elif container == "empty":
        monkeypatch.setattr(_FakeWad, "extract", staticmethod(lambda *_args, **_kwargs: [b""]))
    elif container == "empty_wpk":
        bank = entity.resource_banks[0]
        entity.resource_banks = (replace(bank, binding=replace(bank.binding, kind="WPK")),)
        monkeypatch.setattr(unpack_entity, "WPK", lambda _raw: SimpleNamespace(extract_files=lambda: []))

    stats = unpack_entity.unpack_entity(entity, reader, ctx=ctx)

    component = get_entity_path_component("resource_pack", key)
    entity_folder = format_entity_folder_name(component, entity.entity_alias, entity.entity_name)
    wem_path = ctx.audio_path / reader.version / "SFX" / "resource_packs" / entity_folder / "101.wem"
    report_path = ctx.report_path / reader.version / "resource_packs" / f"_{component}_metadata.yaml"
    assert report_path.is_file()
    assert ":" not in report_path.name
    if container == "audio":
        assert wem_path.read_bytes() == b"wem"
        assert stats.overall_result.value == "success"
    elif container == "metadata":
        assert not wem_path.exists()
        assert stats.overall_result.value == "success"
        assert stats.binding_details[0]["outcome"] == "no_audio"
    else:
        assert not wem_path.exists()
        assert stats.overall_result.value == "error"
        assert "elder_dragon_audio.bnk" in stats.get_simple_summary()
        assert stats.binding_details[0]["error"] in stats.get_simple_summary()


def test_resource_pack_batch_dispatches_string_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """批处理必须把 resource-pack key 交给专用 string consumer。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    calls: list[str] = []
    reader = SimpleNamespace(version="16.16", write_unknown_categories=lambda: None)
    ctx = SimpleNamespace(config=SimpleNamespace(dev_mode=False))
    monkeypatch.setattr(
        unpack_batch,
        "unpack_resource_pack",
        lambda value, *_args, **_kwargs: (
            calls.append(value),
            SimpleNamespace(
                overall_result=UnpackStageResult.SUCCESS,
                file_failures=[],
                binding_details=[],
                get_simple_summary=lambda: "resource pack 解包成功",
            ),
        )[1],
    )

    result = unpack_batch.unpack_resource_packs(reader, [key], max_workers=1, ctx=ctx)

    assert calls == [key]
    assert result.status is ResultStatus.SUCCESS


def test_file_write_failure_retries_only_selected_binding_and_wem(monkeypatch, tmp_path: Path) -> None:
    """容器内写入失败不阻断其他 WEM，重试只重读相关容器并补写失败文件。"""
    key = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    entity = _build_entity(key)
    bank = entity.resource_banks[0]
    other = replace(bank, binding=replace(bank.binding, path="other.bnk", normalized_path="other.bnk", entry_hash="02"))
    entity.resource_banks += (other,)
    wad_path = tmp_path / "game" / bank.binding.wad
    wad_path.parent.mkdir(parents=True)
    wad_path.write_bytes(b"wad")
    ctx = SimpleNamespace(
        game_path=tmp_path / "game",
        audio_path=tmp_path / "audios",
        report_path=tmp_path / "reports",
        game_region="zh_CN",
        include_types=("SFX",),
        exclude_types=(),
        group_by_type=True,
        config=SimpleNamespace(dev_mode=False),
    )
    reader = SimpleNamespace(version="16.16", write_unknown_categories=lambda: None)
    writes: list[int] = []
    reads: list[tuple[str, ...]] = []
    denied = True
    failed_id = 102

    def save(number: int, path: Path) -> None:
        """仅让第一次写入指定文件失败。"""
        writes.append(number)
        if denied and number == failed_id:
            raise PermissionError("access denied")
        path.write_bytes(b"wem")

    def extract(paths, *, raw):
        """保留实际提交给 WAD 的容器范围。"""
        reads.append(tuple(paths))
        return [path.encode() for path in paths]

    def parse(raw):
        """模拟外部容器边界，目录组织与重试逻辑仍由生产代码处理。"""
        numbers = (103,) if raw == b"other.bnk" else (101, 102)
        return SimpleNamespace(
            extract_files=lambda: [
                SimpleNamespace(id=number, data=b"wem", save_file=lambda path, number=number: save(number, path))
                for number in numbers
            ]
        )

    monkeypatch.setattr(unpack_entity, "_get_wad_instance", lambda *_args, **_kwargs: SimpleNamespace(extract=extract))
    monkeypatch.setattr(unpack_entity, "BNK", parse)
    monkeypatch.setattr(AudioEntityData, "from_entity", staticmethod(lambda *_args, **_kwargs: entity))
    monkeypatch.setattr(
        unpack_batch,
        "unpack_resource_pack",
        lambda _key, reader, **kwargs: unpack_entity.unpack_entity(entity, reader, **kwargs),
    )
    original = unpack_batch.execute_tasks([("resource_pack", key, "资源包")], reader, 1, ctx=ctx)
    assert original.status is ResultStatus.PARTIAL
    (failure,) = original.entities[0].failures
    assert failure.unit == "file" and Path(failure.output_path).name == "102.wem"
    assert writes == [101, 102, 103]
    denied = False
    writes.clear()
    retried = unpack_batch.execute_tasks(
        [("resource_pack", key, "资源包")], reader, 1, ctx=ctx, retry_entities=original.entities
    )
    assert retried.status is ResultStatus.SUCCESS
    assert reads[-1] == (bank.binding.path,)
    assert writes == [102]
    assert retried.entities[0].artifacts == (failure.output_path,)
