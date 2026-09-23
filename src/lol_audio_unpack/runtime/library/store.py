"""内容对象发布、单写者互斥与单索引原子提交。"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from contextlib import ExitStack
from pathlib import Path
from threading import RLock
from typing import BinaryIO

import msgpack
from loguru import logger

from lol_audio_unpack.utils.atomic import replace_file

from .index import LibraryIndex
from .types import (
    LibraryBusyError,
    LibraryError,
    MediaRef,
    MergeResult,
    ObjectRef,
    PublishedObject,
    WavRef,
    resolve_path,
)

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_FILE_LOCK_COUNT = 64


class Library:
    """以输出目录为根的资源库；写入须在 with 上下文内进行。

    同一实例可由任务内线程共享；同库第二个实例/进程写入立即报忙。
    只读查询不取得写锁，也不创建输出目录。
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self._mutex = RLock()
        # 分片写锁允许任务内独立文件并行，且内存不随对象总数增长。
        self._files = tuple(RLock() for _ in range(_FILE_LOCK_COUNT))
        self._lock: BinaryIO | None = None

    def __enter__(self) -> Library:
        with self._mutex:
            if self._lock is not None:
                raise LibraryBusyError("该库实例已在写入，不能嵌套进入")
            path = self.resolve("audios/.writer.lock")
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = path.open("a+b")
            try:
                # 固定锁住首字节；锁文件保留，防止删除重建后出现两个不同锁对象。
                if path.stat().st_size == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                stream.close()
                logger.error(f"资源库写入锁不可用: {self.root}: {exc}")
                raise LibraryBusyError(f"资源库已有写入任务或锁不可用: {self.root}") from exc
            self._lock = stream
        return self

    def __exit__(self, *_exc: object) -> None:
        with self._mutex, ExitStack() as writes:
            for lock in self._files:
                writes.enter_context(lock)
            if self._lock is not None:
                # 关闭句柄由操作系统释放锁，进程异常退出也不会留下占用状态。
                self._lock.close()
                self._lock = None

    def resolve(self, path: str) -> Path:
        """返回受库根边界约束的路径，包括已存在的重解析点。"""
        return resolve_path(self.root, path)

    def locate(self, ref: ObjectRef) -> Path:
        """仅在写出链接时定位内容文件，不重新读取或哈希。"""
        path = self.resolve(ref.path)
        if not path.is_file():
            raise LibraryError(f"对象缺失或字节数异常: {ref.digest}")
        return path

    def publish(self, data: bytes) -> PublishedObject:
        """从本次实际取得的完整字节识别内容并发布，返回新增/复用事实。"""
        ref = ObjectRef(hashlib.sha256(data).hexdigest(), len(data))
        with self._file_lock(ref.path):
            self._require_writer()
            target = self.resolve(ref.path)
            if target.exists() or target.is_symlink():
                self.locate(ref)
                return PublishedObject(ref, False)
            replace_file(target, lambda temp: temp.write_bytes(data), write_stage="object")
            return PublishedObject(ref, True)

    def materialize(self, ref: ObjectRef, relative: str) -> str:
        """原子发布可见硬链接；失败时保留原文件，不产生独立媒体副本。"""
        return self.link_file(self.locate(ref), relative)

    def link_file(self, source: Path, relative: str) -> str:
        """把库内已完成的对象或派生文件原子链接到库内可见位置。"""
        with self._file_lock(relative):
            self._require_writer()
            source = self.resolve(source.relative_to(self.root).as_posix())
            target = self.resolve(relative)
            if target.is_file() and source.samefile(target):
                return "reused"
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            created = []
            try:
                for directory in reversed(missing):
                    try:
                        directory.mkdir()
                    except FileExistsError:
                        pass
                    else:
                        created.append(directory)
                if not target.exists():
                    try:
                        # 链接创建本身是原子的，源对象已完整发布；新目标无需再造临时文件、重复 fsync 内容。
                        os.link(source, target)
                        return "hardlink"
                    except FileExistsError:
                        logger.warning("可见目标在写入前出现，改用原子替换：{}", relative)
                    except OSError as exc:
                        raise LibraryError(f"无法创建库内硬链接，请使用支持硬链接的同卷目录: {relative}") from exc

                def write(temp: Path) -> None:
                    temp.unlink()
                    try:
                        os.link(source, temp)
                    except OSError as exc:
                        raise LibraryError(f"无法创建库内硬链接: {relative}") from exc

                replace_file(target, write, write_stage="materialize")
                return "hardlink"
            except (OSError, ValueError):
                # 仅撤掉本次创建且仍为空的目录，不扫描已有目录或删除任何媒体。
                for directory in reversed(created):
                    try:
                        directory.rmdir()
                    except OSError:
                        logger.debug("媒体发布失败后保留已非空或不可清理的目录：{}", directory)
                raise

    @property
    def is_writing(self) -> bool:
        """当前实例是否持有写锁，供同一任务复用写入会话。"""
        return self._lock is not None

    def load(self, version: str, region: str) -> LibraryIndex:
        """只读取指定版本区域；缺失表示空，存在但损坏必须报错。"""
        empty = LibraryIndex(version, region)
        path = self.resolve(empty.path)
        if not path.exists() and not path.is_symlink():
            return empty
        return self._read(path, empty.version, empty.region)

    def merge(
        self,
        version: str,
        region: str,
        media: Iterable[MediaRef] = (),
        *,
        wavs: Iterable[WavRef] = (),
    ) -> MergeResult:
        """原子归并成功引用并保存一份前态；失败保留上次索引。

        仅检查本次提交的对象，未选旧记录无需访问；取消者只提交已经成功的批次。
        无实际变化不写索引，也不刷新备份。
        """
        media, wavs = tuple(media), tuple(wavs)
        with self._mutex:
            self._require_writer()
            old = self.load(version, region)
            index, result = old.merge(media, wavs=wavs)
            if not result.written:
                return result
            target = self.resolve(index.path)
            if target.exists():
                self._write(self.resolve(index.path + ".bak"), old)
            self._write(target, index)
            return result

    def restore(self, version: str, region: str) -> LibraryIndex:
        """显式恢复缺失索引的上一份备份；不覆盖现存损坏或较新索引。"""
        with self._mutex:
            self._require_writer()
            empty = LibraryIndex(version, region)
            target = self.resolve(empty.path)
            if target.exists() or target.is_symlink():
                raise LibraryError("索引仍存在，拒绝以备份覆盖")
            backup = self.resolve(empty.path + ".bak")
            index = self._read(backup, empty.version, empty.region)
            self._write(target, index)
            logger.info(f"已恢复资源库索引备份: {empty.version}/{empty.region}")
            return index

    def _require_writer(self) -> None:
        if self._lock is None:
            raise LibraryError("写入资源库必须先进入 Library 上下文")

    def _file_lock(self, relative: str) -> RLock:
        """仅文件写入用分片互斥；索引与进程锁生命周期仍由全局互斥保护。"""
        with self._mutex:
            self._require_writer()
            key = relative.casefold() if os.name == "nt" else relative
            return self._files[hash(key) % len(self._files)]

    @staticmethod
    def _read(path: Path, version: str, region: str) -> LibraryIndex:
        try:
            data = msgpack.unpackb(path.read_bytes(), raw=False, strict_map_key=False)
            if not isinstance(data, dict):
                raise LibraryError("索引顶层必须是字典")
            return LibraryIndex(version, region, data)
        except (OSError, ValueError, TypeError) as exc:
            raise LibraryError(f"无法读取资源库索引，未覆盖原文件: {path}: {exc}") from exc

    @staticmethod
    def _write(path: Path, index: LibraryIndex) -> None:
        data = msgpack.packb(index.to_dict(), use_bin_type=True)
        replace_file(path, lambda temp: temp.write_bytes(data), write_stage="index")
