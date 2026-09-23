"""内容复用、精确可见路径、派生失效和导出隔离的行为验证。"""

from dataclasses import replace
from pathlib import Path

import pytest
from pyvgmstream.transcode import BatchTranscodeItemResult, BatchTranscodeSummary

from lol_audio_unpack.app.audio_scope import AudioScope
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.library import Library, MediaRef, store
from lol_audio_unpack.runtime.wav import batch
from lol_audio_unpack.runtime.wav.cache import WavCache
from tests.factories import make_wav

pytestmark = pytest.mark.integration
UNIQUE_CONTENTS = 2
LOGICAL_REFS = 3


def make_library(root: Path, *, grouped: bool = False) -> AudioScope:
    """三个皮肤引用两份内容，均保留相同原始 ID。"""
    paths = []
    with Library(root) as writer:
        refs = []
        for i, data in enumerate((b"same", b"same", b"different"), 1):
            ref = MediaRef("champion", "1", 101, writer.publish(data).ref, f"100{i}")
            body = Path("champions") / "1·Hero·英雄" / f"100{i}·皮肤"
            body = Path("VO") / body if grouped else body / "VO"
            path = Path("audios/16.18/zh_CN") / body / "101.wem"
            writer.materialize(ref.object, path.as_posix())
            paths.append(path.relative_to("audios/16.18/zh_CN").as_posix())
            refs.append(ref)
        writer.merge("16.18", "zh_CN", refs)
    return AudioScope(root / "audios/16.18/zh_CN", files=tuple(paths))


def install_converter(monkeypatch):
    """隔离上游转换与工具探测，成功文件仍经过项目完整 WAV 校验。"""
    calls, probes = [], []

    def convert(sources, output_root, *, input_root, **_kwargs):
        calls.append(tuple(sources))
        results = []
        for source in sources:
            output = output_root / source.relative_to(input_root).with_suffix(".wav")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(make_wav())
            results.append(BatchTranscodeItemResult(source, output, 1, output.stat().st_size, None))
        return BatchTranscodeSummary(input_root, output_root, len(results), 0, tuple(results))

    monkeypatch.setattr(batch, "transcode_many", convert)
    monkeypatch.setattr(batch, "require_tool", lambda *args, **kwargs: probes.append((args, kwargs)))
    return calls, probes


@pytest.mark.parametrize("grouped", [False, True])
def test_content_reuse_materializes_all_refs_and_exports_copies(tmp_path, monkeypatch, grouped):
    """两种布局都保留三条身份；缓存命中不探测工具，导出编辑不影响原件。"""
    scope = make_library(tmp_path, grouped=grouped)
    calls, probes = install_converter(monkeypatch)
    options = WavOutputOptions(enabled=True)

    def run(output, *, managed=False):
        return batch.run_batch(
            scope,
            output,
            options=options,
            report_root=tmp_path / "reports",
            overwrite=True,
            cache=WavCache(options, tmp_path, "16.18", "zh_CN"),
            managed=managed,
        )

    first = run(tmp_path / "wavs/16.18/zh_CN", managed=True)
    assert (first.success_count, first.converted_count, first.reused_count) == (3, 2, 1)
    assert len(calls) == len(probes) == 1 and len(calls[0]) == UNIQUE_CONTENTS
    second = run(tmp_path / "export")
    assert (second.success_count, second.converted_count, second.reused_count) == (3, 0, 3)
    assert len(calls) == len(probes) == 1
    visible = (tmp_path / "wavs/16.18/zh_CN" / scope.files[0]).with_suffix(".wav")
    exported = (tmp_path / "export" / scope.files[0]).with_suffix(".wav")
    assert not exported.samefile(visible)
    exported.write_bytes(b"user edit")
    assert visible.read_bytes() == make_wav()


def test_format_change_replaces_current_outputs(tmp_path, monkeypatch):
    """PCM16 改为 float 必须重做，索引数量和输出位置保持不变。"""
    scope = make_library(tmp_path)
    calls, probes = install_converter(monkeypatch)
    options = WavOutputOptions(enabled=True)

    def run(opts):
        return batch.run_batch(
            scope,
            tmp_path / "wavs/16.18/zh_CN",
            options=opts,
            report_root=tmp_path / "reports",
            cache=WavCache(opts, tmp_path, "16.18", "zh_CN"),
            managed=True,
        )

    assert run(options).converted_count == UNIQUE_CONTENTS
    assert run(options).converted_count == 0
    assert run(replace(options, format="float")).converted_count == UNIQUE_CONTENTS
    records = Library(tmp_path).load("16.18", "zh_CN").to_dict()["wavs"]
    assert len(records) == LOGICAL_REFS
    assert {record["format"] for record in records.values()} == {"float"}
    assert not (tmp_path / "wavs/_data").exists()
    assert len(calls) == len(probes) == UNIQUE_CONTENTS


def test_hardlink_failure_keeps_original_without_copy(tmp_path, monkeypatch):
    """硬链接失败不得生成独立媒体文件或损坏内容对象。"""
    with Library(tmp_path) as library:
        obj = library.publish(b"original").ref
        monkeypatch.setattr(store.os, "link", lambda *_: (_ for _ in ()).throw(OSError("cross volume")))
        with pytest.raises(ValueError, match="硬链接"):
            library.materialize(obj, "audios/visible/101.wem")
        assert not library.resolve("audios/visible").exists()
        assert library.locate(obj).read_bytes() == b"original"
