"""验证事件输出的精确路径、任务末尾映射和旧目录隔离。"""

from dataclasses import replace
from pathlib import Path

import msgpack
import pytest

from lol_audio_unpack.app.outputs import save_outputs
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.library import Library, MediaRef
from lol_audio_unpack.runtime.wav import batch, event_output
from lol_audio_unpack.runtime.wav.event_output import EventOutput
from lol_audio_unpack.runtime.wav.job import run_tree
from tests.factories import make_context, make_wav
from tests.runtime.test_wav_cache import install_converter, make_library

pytestmark = pytest.mark.integration
SELECTED_AUDIO_COUNT = 3
EVENT_OUTPUT_COUNT = 4


@pytest.mark.parametrize("later_root_fails", [False, True])
def test_standalone_event_transcode_delivers_known_outputs_even_if_later_root_fails(
    tmp_path, monkeypatch, later_root_fails
):
    """独立 Python 入口使用已有映射；后续目录越界失败也不丢弃先前转换结果。"""
    scope = make_library(tmp_path)
    save_outputs(tmp_path, "16.18", "zh_CN", "champion", "1", scope.resolve_files())
    install_converter(monkeypatch)
    ctx = make_context(tmp_path)
    write_mapping(ctx.version_path("hash", "16.18"), ("1001·皮肤/VO/101.wem", "1002·皮肤/VO/101.wem"))
    roots = (scope.root, tmp_path / "outside") if later_root_fails else (scope.root,)
    payload = run_tree(
        ctx=ctx, version="16.18", wav_output=WavOutputOptions(enabled=True, group_by_event=True), audio_roots=roots
    )
    assert payload["status"] == ("warning" if later_root_fails else "success")
    assert payload["processed_file_count"] == SELECTED_AUDIO_COUNT
    assert (ctx.version_path("wav_event", "16.18") / "champions/1·Hero·英雄/1001·皮肤/VO/Play_Attack/101.wav").is_file()
    assert payload["batches"][0].output_root == ctx.version_path("wav_event", "16.18")
    assert not ctx.version_path("wav", "16.18").exists()


def write_mapping(root: Path, paths: tuple[str, ...], *, integrated: bool = False) -> Path:
    """记录明确的事件关系：首个音频属两个事件，第二个属一个，第三个无关联。"""
    skins = {
        "1001": {
            "events": {"VO": {"Play_Attack": ["101"], "Play_Move": ["101"]}},
            "audioPaths": {"VO": {"Play_Attack": [paths[0]], "Play_Move": [paths[0]]}},
        },
        "1002": {
            "events": {"VO": {"Play_Death": ["101"]}},
            "audioPaths": {"VO": {"Play_Death": [paths[1]]}},
        },
    }
    payload = {"metadata": {"gameVersion": "16.18"}, "championId": "1", "skins": skins}
    if integrated:
        payload = {
            "metadata": payload["metadata"],
            "data": {
                "championId": "1",
                "skins": [
                    {"id": key, "events": {"VO": {"mapping": value["events"]["VO"]}}, "audioPaths": value["audioPaths"]}
                    for key, value in skins.items()
                ],
            },
        }
    path = root / ("integrated" if integrated else "") / "champions/1.msgpack"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(msgpack.packb(payload, use_bin_type=True))
    return path


@pytest.mark.parametrize(("grouped", "integrated"), [(False, False), (True, False), (False, True)])
def test_event_export_uses_later_mapping_without_touching_old_wavs(tmp_path, monkeypatch, grouped, integrated):
    """映射晚于转换生成也可分类；同 ID 三个皮肤保持独立，旧平铺输出完全保留。"""
    scope = make_library(tmp_path, grouped=grouped)
    install_converter(monkeypatch)
    output = tmp_path / "wavs/16.18/zh_CN"
    old = (output / scope.files[0]).with_suffix(".wav")
    old.parent.mkdir(parents=True)
    old.write_bytes(b"user's old WAV")
    logical = tuple(
        "VO/" + "/".join(Path(value).parts[-2:]) if grouped else "/".join(Path(value).parts[-3:])
        for value in scope.files
    )
    hashes = tmp_path / "hashes/16.18/zh_CN"
    with EventOutput(
        audio_root=scope.root, hash_root=hashes, version="16.18", scratch_root=tmp_path / "scratch"
    ) as session:
        session.run_batch(
            scope, output, options=WavOutputOptions(enabled=True, group_by_event=True), report_root=tmp_path / "reports"
        )
        assert not list(output.rglob("Play_Attack/101.wav"))
        write_mapping(hashes, logical, integrated=integrated)
        (result,) = session.finish()

    bodies = (
        (
            "VO/champions/1·Hero·英雄/1001·皮肤",
            "VO/champions/1·Hero·英雄/1002·皮肤",
            "VO/champions/1·Hero·英雄/1003·皮肤",
        )
        if grouped
        else (
            "champions/1·Hero·英雄/1001·皮肤/VO",
            "champions/1·Hero·英雄/1002·皮肤/VO",
            "champions/1·Hero·英雄/1003·皮肤/VO",
        )
    )
    expected = {
        output / bodies[0] / "Play_Attack/101.wav",
        output / bodies[0] / "Play_Move/101.wav",
        output / bodies[1] / "Play_Death/101.wav",
        output / bodies[2] / "未关联事件/101.wav",
    }
    assert set(output.rglob("*.wav")) == expected | {old}
    assert all(path.read_bytes() == make_wav() for path in expected)
    assert old.read_bytes() == b"user's old WAV"
    assert all(not path.samefile(old) for path in expected)
    copies = sorted(expected)
    assert not copies[0].samefile(copies[1])
    assert (
        result.success_count,
        result.failed_count,
        result.classified_count,
        result.unclassified_count,
        result.output_count,
    ) == (3, 0, 2, 1, 4)
    assert batch.read_batch_result(result.report_path) == result
    # 事件导出不新增标准 WAV 格式记录。
    assert not batch.WavCache(result.options, tmp_path, "16.18", "zh_CN").index.to_dict()["wavs"]


@pytest.mark.parametrize("mapping_state", ["missing", "corrupt", "ids_only", "other_version"])
def test_unusable_mapping_keeps_every_selected_audio(tmp_path, monkeypatch, mapping_state):
    """无映射、坏映射、旧无路径映射和版本不符时不猜测 ID、不遗漏音频。"""
    scope = make_library(tmp_path)
    install_converter(monkeypatch)
    hashes = tmp_path / "hashes/16.18/zh_CN"
    path = hashes / "champions/1.msgpack"
    path.parent.mkdir(parents=True)
    if mapping_state == "corrupt":
        path.write_bytes(b"invalid msgpack")
    elif mapping_state != "missing":
        payload = {
            "metadata": {"gameVersion": "16.17" if mapping_state == "other_version" else "16.18"},
            "skins": {"1001": {"events": {"VO": {"Play_Attack": ["101"]}}}},
        }
        path.write_bytes(msgpack.packb(payload, use_bin_type=True))
    output = tmp_path / "export/16.18/zh_CN"
    with EventOutput(
        audio_root=scope.root, hash_root=hashes, version="16.18", scratch_root=tmp_path / "scratch"
    ) as session:
        session.run_batch(
            scope, output, options=WavOutputOptions(enabled=True, group_by_event=True), report_root=tmp_path / "reports"
        )
        (result,) = session.finish()
    assert result.success_count == result.plain_count == SELECTED_AUDIO_COUNT
    assert result.unclassified_count == 0
    assert {path.relative_to(output).as_posix() for path in output.rglob("*.wav")} == {
        f"champions/1·Hero·英雄/100{i}·皮肤/VO/101.wav" for i in (1, 2, 3)
    }


@pytest.mark.parametrize("integrated", [False, True])
def test_valid_empty_mapping_uses_unassociated_event_directory(tmp_path, monkeypatch, integrated):
    """显式空路径关系表示有效映射，所有选中音频应进入未关联事件。"""
    scope = make_library(tmp_path)
    install_converter(monkeypatch)
    group = {"events": {}, "audioPaths": {}}
    payload = {"championId": "1", "skins": {"1001": group}}
    if integrated:
        payload = {"data": {"championId": "1", "skins": [{"id": "1001", **group}]}}
    hashes = tmp_path / "hashes"
    path = hashes / "champions/1.msgpack"
    path.parent.mkdir(parents=True)
    path.write_bytes(msgpack.packb(payload, use_bin_type=True))
    output = tmp_path / "export"
    with EventOutput(
        audio_root=scope.root, hash_root=hashes, version="16.18", scratch_root=tmp_path / "scratch"
    ) as session:
        session.run_batch(
            scope, output, options=WavOutputOptions(group_by_event=True), report_root=tmp_path / "reports"
        )
        (result,) = session.finish()
    assert result.unclassified_count == SELECTED_AUDIO_COUNT
    assert result.plain_count == 0
    assert {path.relative_to(output).as_posix() for path in output.rglob("*.wav")} == {
        f"champions/1·Hero·英雄/100{i}·皮肤/VO/未关联事件/101.wav" for i in (1, 2, 3)
    }


def test_default_event_root_does_not_mix_with_previous_plain_output(tmp_path, monkeypatch):
    """同版本重复转码切换布局时，普通与事件 WAV 分开，旧文件内容保持不变。"""
    scope = make_library(tmp_path)
    save_outputs(tmp_path, "16.18", "zh_CN", "champion", "1", scope.resolve_files())
    install_converter(monkeypatch)
    ctx = make_context(tmp_path)
    run_tree(ctx=ctx, version="16.18", wav_output=WavOutputOptions(enabled=True))
    plain = {path: path.read_bytes() for path in ctx.version_path("wav", "16.18").rglob("*.wav")}
    write_mapping(ctx.version_path("hash", "16.18"), ("1001·皮肤/VO/101.wem", "1002·皮肤/VO/101.wem"))
    payload = run_tree(ctx=ctx, version="16.18", wav_output=WavOutputOptions(enabled=True, group_by_event=True))
    assert {path: path.read_bytes() for path in ctx.version_path("wav", "16.18").rglob("*.wav")} == plain
    assert len(tuple(ctx.version_path("wav_event", "16.18").rglob("*.wav"))) == EVENT_OUTPUT_COUNT
    assert payload["plain_file_count"] == 0


def test_default_event_root_falls_back_per_entity_and_reports_both_roots(tmp_path, monkeypatch):
    """一个对象有映射不代表其他对象也有；最终报告只列实际交付的两种目录。"""
    scope = make_library(tmp_path)
    sources = scope.resolve_files()
    other = scope.root / "champions/2·Other·其他/2000·基础皮肤/VO/202.wem"
    other.parent.mkdir(parents=True)
    with Library(tmp_path) as writer:
        ref = MediaRef("champion", "2", 202, writer.publish(b"another audio").ref, "2000")
        writer.materialize(ref.object, other.relative_to(tmp_path).as_posix())
        writer.merge("16.18", "zh_CN", [ref])
    save_outputs(tmp_path, "16.18", "zh_CN", "champion", "1", sources)
    save_outputs(tmp_path, "16.18", "zh_CN", "champion", "2", (other,))
    install_converter(monkeypatch)
    ctx = make_context(tmp_path)
    write_mapping(ctx.version_path("hash", "16.18"), ("1001·皮肤/VO/101.wem", "1002·皮肤/VO/101.wem"))
    payload = run_tree(ctx=ctx, version="16.18", wav_output=WavOutputOptions(enabled=True, group_by_event=True))
    plain = ctx.version_path("wav", "16.18")
    event = ctx.version_path("wav_event", "16.18")
    assert (plain / "champions/2·Other·其他/2000·基础皮肤/VO/202.wav").is_file()
    assert not (event / "champions/2·Other·其他").exists()
    assert payload["plain_file_count"] == 1
    assert payload["unclassified_file_count"] == 1
    assert set(payload["wav_roots"]) == {str(plain), str(event)}


def test_failed_event_copy_reports_partial_output_and_existing_files_are_skipped(tmp_path, monkeypatch):
    """一个事件目标无法写入时保留另一个；重新导出不覆盖用户修改过的事件文件。"""
    scope = make_library(tmp_path)
    scope = replace(scope, files=scope.files[:1])
    install_converter(monkeypatch)
    hashes = tmp_path / "hashes/16.18/zh_CN"
    write_mapping(hashes, ("1001·皮肤/VO/101.wem", "1002·皮肤/VO/101.wem"))
    output = tmp_path / "export/16.18/zh_CN"
    broken = output / "champions/1·Hero·英雄/1001·皮肤/VO/Play_Move"
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"a file occupies the directory")
    with EventOutput(
        audio_root=scope.root, hash_root=hashes, version="16.18", scratch_root=tmp_path / "scratch"
    ) as session:
        for _ in range(2):
            session.run_batch(
                scope,
                output,
                options=WavOutputOptions(enabled=True, group_by_event=True),
                report_root=tmp_path / "reports",
            )
            (result,) = session.finish()
            if not result.output_count:
                break
            assert result.status == "partial"
            assert result.success_count == 0 and result.output_count == result.failed_count == 1
            successful = output / "champions/1·Hero·英雄/1001·皮肤/VO/Play_Attack/101.wav"
            successful.write_bytes(b"user edit")
        assert result.failed_count == 1
        assert successful.read_bytes() == b"user edit"


def test_event_folder_collisions_do_not_merge_relations(tmp_path, monkeypatch):
    """大小写、非法字符和保留名经整理后仍保留各自事件文件，且没有目录越界。"""
    scope = replace(make_library(tmp_path), files=("champions/1·Hero·英雄/1001·皮肤/VO/101.wem",))
    install_converter(monkeypatch)
    path = tmp_path / "hashes/champions/1.msgpack"
    path.parent.mkdir(parents=True)
    names = ("Play_Attack", "play_attack", "a:b", "ab", "CON", "未关联事件")
    path.write_bytes(
        msgpack.packb(
            {
                "skins": {
                    "1001": {
                        "events": {"VO": {name: ["101"] for name in names}},
                        "audioPaths": {"VO": {name: ["1001·皮肤/VO/101.wem"] for name in names}},
                    }
                }
            },
            use_bin_type=True,
        )
    )
    output = tmp_path / "export"
    with EventOutput(
        audio_root=scope.root, hash_root=path.parent.parent, version="16.18", scratch_root=tmp_path / "scratch"
    ) as session:
        session.run_batch(
            scope, output, options=WavOutputOptions(enabled=True, group_by_event=True), report_root=tmp_path / "reports"
        )
        (result,) = session.finish()
    outputs = tuple(output.rglob("*.wav"))
    assert result.success_count == 1 and result.output_count == len(names)
    assert len({path.parent.name.casefold() for path in outputs}) == len(names)
    assert all(path.read_bytes() == make_wav() for path in outputs)
