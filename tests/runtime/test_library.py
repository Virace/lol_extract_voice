"""验证内容库的归属并集、持久化故障和真实文件系统边界。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path, PureWindowsPath
from shutil import copytree

import msgpack
import pytest

from lol_audio_unpack.runtime.library import (
    Library,
    LibraryBusyError,
    LibraryError,
    MediaRef,
    ObjectRef,
    WavRef,
)
from lol_audio_unpack.runtime.library.types import resolve_path
from lol_audio_unpack.utils import atomic
from lol_audio_unpack.utils.atomic import ArtifactWriteError

pytestmark = pytest.mark.unit


def make_ref(library: Library, data: bytes = b"actual WEM", **changes: object) -> MediaRef:
    """用实际发布字节建立精确引用，替换字段用于不同归属。"""
    ref = MediaRef("champion", "1", 100, library.publish(data).ref, "1000")
    return replace(ref, **changes)


def test_union_repeat_and_exact_identity(tmp_path):
    """重复十次不改文件，局部成功并集等于完整输入，同 ID 在不同皮肤中保留各自归属。"""
    with Library(tmp_path / "library") as library:
        first = make_ref(library)
        other = make_ref(library, b"SFX", media_id=200)
        same_id = make_ref(library, b"different skin", skin_id="1001")
        hero = replace(other, entity_id="3")
        refs = [first, other, same_id, hero]
        library.merge("16.18", "zh_CN", [first])
        library.merge("16.18", "zh_CN", [other, same_id])
        library.merge("16.18", "zh_CN", [hero])
        index = library.load("16.18", "zh_CN")
        path = library.resolve(index.path)
        before = path.read_bytes(), path.stat().st_mtime_ns
        for _ in range(10):
            result = library.merge("16.18", "zh_CN", refs)
            assert (result.added, result.updated, result.reused, result.written) == (0, 0, 4, False)
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        assert len(list(index.iter_media())) == len(refs)
        with Library(tmp_path / "complete") as full:
            for data in (b"actual WEM", b"SFX", b"different skin"):
                full.publish(data)
            full.merge("16.18", "zh_CN", refs)
            assert full.load("16.18", "zh_CN").to_dict() == index.to_dict()


def test_versions_regions_and_changed_source(tmp_path):
    """先新后旧、跨版本换号、英语别名和同 ID 实际字节变化均保留正确引用。"""
    with Library(tmp_path) as library:
        for version, data, media_id in (("4", b"X", 400), ("3", b"Z", 300), ("2", b"Y", 200), ("1", b"X", 100)):
            ref = make_ref(library, data, media_id=media_id)
            library.merge(version, "default", [ref])
            assert list(library.load(version, "en_US").iter_media()) == [ref]
        unique_contents = {b"X", b"Y", b"Z"}
        assert len(list((tmp_path / "audios/_data").rglob("*.wem"))) == len(unique_contents)
        old = make_ref(library, b"X")
        new = make_ref(library, b"changed")
        library.merge("1", "zh_CN", [old])
        result = library.merge("1", "zh_CN", [new])
        assert result.updated == 1
        assert list(library.load("1", "zh_CN").iter_media()) == [new]
        assert list(library.load("1", "en_US").iter_media())[0].object == old.object


def test_parallel_publish_and_writer_lock(tmp_path):
    """任务内线程只发布一份对象，第二写者立即报忙，退出后可重新取得锁。"""
    with Library(tmp_path) as library:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(library.publish, [b"same bytes"] * 32))
        assert sum(result.created for result in results) == 1
        assert len({result.ref for result in results}) == 1
        with pytest.raises(LibraryBusyError), Library(tmp_path):
            pass
    with Library(tmp_path) as library:
        assert not library.publish(b"same bytes").created
    with pytest.raises(LibraryError, match="上下文"):
        library.publish(b"new bytes")


def hold_writer(root, ready, release):
    """在独立进程持有写锁，供父进程验证跨进程互斥。"""
    with Library(root):
        ready.set()
        release.wait(10)


def test_process_lock_released_after_termination(tmp_path):
    """异常结束的写入进程不会留下无法解除的逻辑占用。"""
    context = get_context("spawn")
    ready, release = context.Event(), context.Event()
    process = context.Process(target=hold_writer, args=(tmp_path, ready, release))
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(LibraryBusyError), Library(tmp_path):
            pass
    finally:
        process.terminate()
        process.join(10)
    assert not process.is_alive()
    with Library(tmp_path) as library:
        assert library.publish(b"after terminated task").created


def test_object_reuse_does_not_read_existing_content(tmp_path, monkeypatch):
    """每次识别新输入，但相同摘要的已有对象只核对大小。"""
    with Library(tmp_path) as library:
        item = library.publish(b"actual bytes")
        path = library.locate(item.ref)
        monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("不能重读已有对象"))
        assert not library.publish(b"actual bytes").created
        path.unlink()
        assert library.publish(b"actual bytes").created


def test_unpublished_object_rejected_and_failed_publish_leaves_no_index(tmp_path, monkeypatch):
    """对象失败不发布半成品，不允许索引引用尚未取得的内容。"""
    with Library(tmp_path) as library:
        valid = make_ref(library)
        library.merge("1", "zh_CN", [valid])
        monkeypatch.setattr(atomic.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(ArtifactWriteError):
            library.publish(b"cannot finish")
        assert list(library.load("1", "zh_CN").iter_media()) == [valid]
        assert len(list((tmp_path / "audios/_data").rglob("*.wem"))) == 1


@pytest.mark.parametrize("fault", ["backup", "index"])
def test_failed_index_replace_preserves_previous_success(tmp_path, monkeypatch, fault):
    """备份或正式索引原子替换失败时，不丢旧成功记录。"""
    with Library(tmp_path) as library:
        first = make_ref(library)
        library.merge("1", "zh_CN", [first])
        second = make_ref(library, b"second", media_id=200)
        original = atomic.os.replace

        def fail_replace(source, target):
            if str(target).endswith(".bak" if fault == "backup" else ".msgpack"):
                raise OSError("replace denied")
            return original(source, target)

        monkeypatch.setattr(atomic.os, "replace", fail_replace)
        with pytest.raises(ArtifactWriteError):
            library.merge("1", "zh_CN", [second])
        assert list(library.load("1", "zh_CN").iter_media()) == [first]
        assert library.locate(second.object).is_file()


@pytest.mark.parametrize("payload", [b"invalid", msgpack.packb(None), msgpack.packb({"schema": 999})])
def test_corrupt_index_is_never_overwritten(tmp_path, payload):
    """存在的损坏或未知版本索引不能按空库覆盖。"""
    with Library(tmp_path) as library:
        first = make_ref(library)
        library.merge("1", "zh_CN", [first])
        target = library.resolve(library.load("1", "zh_CN").path)
        target.write_bytes(payload)
        with pytest.raises(LibraryError):
            library.merge("1", "zh_CN", [first])
        with pytest.raises(LibraryError):
            library.restore("1", "zh_CN")
        assert target.read_bytes() == payload


def test_missing_index_restore_or_reextract_and_bad_backup(tmp_path):
    """索引丢失可显式恢复前态或按实际重新提取建立，新索引不猜历史归属。"""
    with Library(tmp_path) as library:
        first = make_ref(library)
        second = make_ref(library, b"second", media_id=200)
        library.merge("1", "zh_CN", [first])
        library.merge("1", "zh_CN", [second])
        target = library.resolve(library.load("1", "zh_CN").path)
        target.unlink()
        assert list(library.restore("1", "zh_CN").iter_media()) == [first]
        target.unlink()
        backup = Path(str(target) + ".bak")
        backup.write_bytes(b"invalid")
        with pytest.raises(LibraryError):
            library.restore("1", "zh_CN")
        assert not target.exists()
        library.merge("1", "zh_CN", [second])
        assert list(library.load("1", "zh_CN").iter_media()) == [second]
        assert not library.publish(b"actual WEM").created


def test_wav_record_replaces_current_output(tmp_path):
    """格式切换覆盖固定路径记录，WEM 同内容换 ID 保留两个键。"""
    with Library(tmp_path) as library:
        first = make_ref(library)
        second = replace(first, media_id=200)
        library.merge("1", "zh_CN", [first, second])
        path = "wavs/1/zh_CN/champions/1/100.wav"
        library.merge("1", "zh_CN", wavs=[WavRef(path, first.object.digest, "pcm16")])
        library.merge("1", "zh_CN", wavs=[WavRef(path, first.object.digest, "float")])
        payload = library.load("1", "zh_CN").to_dict()
        assert payload["wavs"] == {path: {"digest": first.object.digest, "format": "float"}}
        assert payload["champions"] == {"1": {"1000": {"100": first.object.digest, "200": first.object.digest}}}
        assert (payload["schema"], payload["version"], payload["algorithm"], payload["region"]) == (
            2,
            "1",
            "sha256",
            "zh_CN",
        )


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/absolute",
        "C:/outside",
        "C:relative",
        "a/../../x",
        "a\\..\\x",
        "a/file:stream",
        "a/../",
        "a/ /file",
    ],
)
def test_unsafe_paths_rejected(tmp_path, path):
    """相对字段不能通过 Windows/POSIX 路径语义逃逸。"""
    with pytest.raises(LibraryError):
        Library(tmp_path).resolve(path)


@pytest.mark.parametrize("prefixes", [(False, True), (True, False), (True, True), (False, False)])
@pytest.mark.parametrize(
    "case",
    [
        ("H:/库 空格", "h:/库 空格/audios/file.wem", True),
        ("H:/库 空格", "H:/库 空格-外部/file.wem", False),
        ("H:/库 空格", "D:/库 空格/audios/file.wem", False),
        ("//server/share/库", "//SERVER/share/库/audios/file.wem", True),
        ("//server/share/库", "//server/share/库外/file.wem", False),
        ("//server/share/库", "//server/other/库/audios/file.wem", False),
    ],
)
def test_resolved_windows_path_boundaries(tmp_path, monkeypatch, case, prefixes):
    """系统返回普通或扩展路径时，库内同路径可用，库外仍被拒绝。"""
    root = tmp_path / "library"
    boundary, target, allowed = case
    resolved = []
    for value, extended in zip((boundary, target), prefixes, strict=True):
        text = str(PureWindowsPath(value))
        if extended:
            text = "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
        resolved.append(PureWindowsPath(text))
    # 只固定操作系统解析结果，比较与拒绝行为走公开路径入口。
    monkeypatch.setattr(Path, "resolve", lambda path: resolved[0] if path == root else resolved[1])
    if allowed:
        assert resolve_path(root, "audios/file.wem") == root / "audios/file.wem"
    else:
        with pytest.raises(LibraryError, match="路径超出资源库"):
            resolve_path(root, "audios/file.wem")


def test_copy_library_and_reparse_escape(tmp_path):
    """整库复制到新根无需改索引，重解析点导向库外时明确拒绝。"""
    old_root = tmp_path / "原目录 空格"
    with Library(old_root) as library:
        ref = make_ref(library)
        library.merge("1", "zh_CN", [ref])
    new_root = tmp_path / "新目录"
    # 此处验证引用不绑定旧根；目录 rename 在本机普通文件对照中也会被外部占用短暂阻止。
    # 真实 rename 搬迁另作隔离文件系统验证，不把 Windows 瞬时共享锁变成行为门禁。
    copytree(old_root, new_root)
    library = Library(new_root)
    restored = next(library.load("1", "zh_CN").iter_media())
    located = library.locate(restored.object)
    assert located.is_relative_to(new_root)
    assert located.read_bytes() == b"actual WEM"
    outside = tmp_path / "outside"
    outside.mkdir()
    link = new_root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"本机不能创建符号链接: {exc}")
    with pytest.raises(LibraryError):
        library.resolve("escape/file.wem")
