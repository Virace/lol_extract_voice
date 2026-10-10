"""在单次 WAV 任务内暂存转码结果，再按精确事件关系输出独立文件。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import unquote

from loguru import logger

from ...app.artifacts import find_mapping
from ...app.audio_scope import AudioScope
from ...app.mapping_preview import normalize_mapping
from ...app.outputs import split_audio
from ...manager.files import read_data
from ...runtime.library.types import relative_path, resolve_path
from ...utils.atomic import replace_file
from ...utils.common import sanitize_filename
from ._runtime import build_output_path
from .batch import WavBatchResult, WavFailure, _persist_result, run_batch

EVENT_SESSION_KEY = "wav_event_output"
_UNMAPPED = "未关联事件"
_FOLDER_LIMIT = 100
_GROUPS = {"champions": "skins", "maps": "map", "resource_packs": "resourcePacks"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _folder_names(names: set[str]) -> dict[str, str]:
    """为非法字符、大小写和保留目录名冲突生成稳定的事件目录名。"""
    cleaned = {name: sanitize_filename(name)[:_FOLDER_LIMIT].rstrip(" .") for name in names}
    counts: dict[str, int] = {}
    for value in cleaned.values():
        counts[value.casefold()] = counts.get(value.casefold(), 0) + 1
    result = {}
    for name, value in cleaned.items():
        folder = value
        reserved = value.split(".", 1)[0].upper() in _RESERVED or value.casefold() == _UNMAPPED.casefold()
        if value != name or counts[value.casefold()] > 1 or reserved:
            suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
            folder = f"{value}·{suffix}"
        result[name] = folder
    return result


class EventOutput:
    """仅持有本次转码中间结果，不管理旧输出或创建 WAV 内容索引。"""

    def __init__(self, *, audio_root: Path, hash_root: Path | None, version: str, scratch_root: Path) -> None:
        """记录本次来源和映射边界，映射在最终输出时读取。

        Args:
            audio_root: 本次固定版本、语言的 WEM 根目录。
            hash_root: 同一版本、语言的映射根；缺失时保留普通目录。
            version: 本次固定的游戏版本。
            scratch_root: 本次转码允许使用的临时根目录。
        """
        self.audio_root = audio_root.resolve()
        self.hash_root = hash_root
        self.version = version
        self.scratch_root = scratch_root
        self.tree_payload: dict | None = None
        self._scratch = None
        self._pending: list[tuple[WavBatchResult, Path, Path, bool, tuple[Path, ...]]] = []
        # None 表示无法分类；空字典表示可用映射中确实没有任何关联。
        self._mappings: dict[tuple[str, str], dict[str, tuple[str, ...]] | None] = {}

    def __enter__(self) -> EventOutput:
        """建立本任务专用暂存目录，开始独立输出会话。"""
        self.scratch_root.mkdir(parents=True, exist_ok=True)
        self._scratch = TemporaryDirectory(prefix=".wav-events-", dir=self.scratch_root)
        logger.info("WAV 事件输出开始，原始音频与已有输出目录保持不变")
        return self

    def __exit__(self, *_args) -> None:
        """释放本任务拥有的中间文件，不触碰最终输出。"""
        if self._scratch is not None:
            self._scratch.cleanup()

    @property
    def has_pending(self) -> bool:
        """判断是否有本轮已执行、尚未交付的转码批次。"""
        return bool(self._pending)

    def run_batch(
        self,
        scope: AudioScope,
        output_root: Path,
        *,
        fallback_root: Path | None = None,
        overwrite: bool = False,
        **kwargs,
    ) -> WavBatchResult:
        """暂存本次转码，为后续映射阶段保留最终输出位置和原覆盖策略。"""
        if self._scratch is None:
            raise RuntimeError("事件输出会话尚未启动")
        try:
            sources = scope.resolve_files()
        except (OSError, ValueError):
            # 交由既有批处理边界返回 typed 失败，不把失效选择变成未捕获异常。
            sources = ()
        scratch = Path(self._scratch.name) / str(len(self._pending))
        result = run_batch(scope, scratch, overwrite=True, **kwargs)
        self._pending.append(
            (result, output_root.resolve(), (fallback_root or output_root).resolve(), overwrite, sources)
        )
        return result

    def _load_mapping(self, entity_dir: str, entity_id: str) -> dict[str, tuple[str, ...]] | None:
        """只接收映射中明确列出的路径，旧 ID-only 映射不能猜测文件归属。"""
        key = entity_dir, entity_id
        if key in self._mappings:
            return self._mappings[key]
        index: dict[str, set[str]] = {}
        self._mappings[key] = None
        if self.hash_root is None:
            return None
        try:
            path = find_mapping(self.hash_root, entity_dir=entity_dir, entity_id=entity_id)
            if path is None:
                logger.info("{} {} 没有可用事件映射，WAV 保留普通目录", entity_dir, entity_id)
                return None
            payload = read_data(path, log_errors=False)
            metadata = payload.get("metadata", {})
            if metadata.get("gameVersion", self.version) != self.version:
                raise ValueError("映射版本与本次音频不匹配")
            mapping = normalize_mapping(payload, entity_type=entity_dir, entity_id=entity_id) or {}
            id_key = {"champions": "championId", "maps": "mapId", "resource_packs": "resourcePackKey"}[entity_dir]
            if str(mapping.get(id_key, entity_id)) != entity_id:
                raise ValueError("映射实体与本次音频不匹配")
            groups = mapping.get(_GROUPS[entity_dir], {})
            if not any(isinstance(group.get("audioPaths"), dict) for group in groups.values()):
                raise ValueError("映射缺少可用的精确音频路径关系")
            for group in groups.values():
                for category, events in group.get("audioPaths", {}).items():
                    for name, paths in events.items():
                        ids = {str(value) for value in group.get("events", {}).get(category, {}).get(name, ())}
                        for value in paths:
                            logical = relative_path(str(value))
                            if Path(logical).stem in ids:
                                index.setdefault(logical, set()).add(str(name))
            names = _folder_names({name for values in index.values() for name in values})
            result = {logical: tuple(names[name] for name in sorted(values)) for logical, values in index.items()}
            self._mappings[key] = result
            if not result:
                logger.info("{} {} 的映射有效但没有关联音频，WAV 放入未关联事件目录", entity_dir, entity_id)
            return result
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("{} {} 的事件映射不可用，WAV 保留普通目录：{}", entity_dir, entity_id, exc)
            return None

    def _targets(
        self, source: Path, scope_root: Path, output_root: Path, fallback_root: Path
    ) -> tuple[tuple[Path, ...], Path, bool]:
        """在完整镜像路径的文件名之前插入事件层，保持不同皮肤和 ID 的身份。"""
        source.relative_to(self.audio_root)
        entity_root, logical, _, _ = split_audio(source)
        entity_dir = entity_root.parent.name
        entity_id = unquote(entity_root.name.split("·", 1)[0])
        mapping = self._load_mapping(entity_dir, entity_id)
        has_mapping = mapping is not None
        root = output_root if has_mapping else fallback_root
        base = build_output_path(source, audio_root=scope_root, wav_root=root)
        folders = mapping.get(logical, (_UNMAPPED,)) if has_mapping else ()
        # 所有路径都以本次输出根为边界，拒绝经现有符号链接越出用户选择的位置。
        paths = (
            tuple(
                resolve_path(root, (base.parent / folder / base.name).relative_to(root).as_posix())
                for folder in folders
            )
            if folders
            else (resolve_path(root, base.relative_to(root).as_posix()),)
        )
        return paths, root, has_mapping

    def finish(self) -> tuple[WavBatchResult, ...]:
        """使用任务末尾的映射交付全部已转换文件，复制失败保留可靠的部分完成事实。"""
        results = []
        for batch, output_root, fallback_root, overwrite, sources in self._pending:
            started = monotonic()
            failures = []
            failed_sources = {Path(item.source_path): item for item in batch.failures}
            success = skipped = classified = unclassified = plain = written = 0
            roots: dict[Path, None] = {}
            for source in sources:
                try:
                    outputs, root, has_mapping = self._targets(source, batch.scope.root, output_root, fallback_root)
                except (OSError, ValueError) as exc:
                    failures.append(WavFailure(str(source), str(output_root), str(exc)))
                    continue
                if source in failed_sources:
                    failures.append(replace(failed_sources[source], output_path=str(outputs[0])))
                    continue
                staged = build_output_path(source, audio_root=batch.scope.root, wav_root=batch.output_root)
                if not staged.is_file():
                    if not batch.error_message:
                        failures.append(WavFailure(str(source), str(outputs[0]), "本次转码结果未能暂存，未输出文件"))
                    continue
                pending = tuple(path for path in outputs if overwrite or not path.exists())
                errors = []
                for output in pending:
                    try:
                        replace_file(
                            output,
                            lambda temp, source=staged: shutil.copyfile(source, temp),
                            write_stage="wav-event-export",
                        )
                        written += 1
                        roots[root] = None
                    except OSError as exc:
                        errors.append(f"{output}: {exc}")
                if errors:
                    failures.append(WavFailure(str(source), str(outputs[0]), "；".join(errors)))
                else:
                    success += bool(pending)
                    skipped += not pending
                    roots[root] = None
                    if not has_mapping:
                        plain += 1
                    elif outputs[0].parent.name == _UNMAPPED:
                        unclassified += 1
                    else:
                        classified += 1
            result = _persist_result(
                replace(
                    batch,
                    output_root=next(iter(roots), output_root),
                    overwrite=overwrite,
                    success_count=success,
                    skipped_count=skipped,
                    failed_count=len(failures),
                    failures=tuple(failures),
                    duration_seconds=batch.duration_seconds + monotonic() - started,
                    classified_count=classified,
                    unclassified_count=unclassified,
                    plain_count=plain,
                    output_count=written,
                    output_roots=tuple(roots),
                )
            )
            results.append(result)
            log = logger.warning if result.failed_count or result.error_message else logger.success
            log(
                "WAV 输出结束：成功 {}、跳过 {}、失败 {} 个音频；关联事件 {}、未关联 {}、普通布局 {}；写入 {} 个文件",
                success,
                skipped,
                result.failed_count,
                classified,
                unclassified,
                plain,
                written,
            )
        self._pending.clear()
        return tuple(results)

    def finish_tree(self) -> dict:
        """更新默认转码的 typed 事实和原报告，不把暂存结果当成已落盘的最终产物。"""
        batches = self.finish()
        payload = dict(self.tree_payload or {})
        errors = [*payload.get("errors", ()), *(batch.error_message for batch in batches if batch.error_message)]
        payload.pop("pending_event_output", None)
        payload.update(
            status="warning" if errors or any(batch.status != "success" for batch in batches) else "success",
            processed_file_count=sum(batch.success_count for batch in batches),
            failed_file_count=sum(batch.failed_count for batch in batches),
            skipped_file_count=sum(batch.skipped_count for batch in batches),
            converted_file_count=sum(batch.converted_count for batch in batches),
            reused_file_count=sum(batch.reused_count for batch in batches),
            produced_file_count=sum(batch.output_count for batch in batches),
            classified_file_count=sum(batch.classified_count for batch in batches),
            unclassified_file_count=sum(batch.unclassified_count for batch in batches),
            plain_file_count=sum(batch.plain_count for batch in batches),
            unconfirmed_file_count=sum(batch.unconfirmed_count for batch in batches),
            errors=list(dict.fromkeys(errors)),
            batch_reports=[str(batch.report_path) for batch in batches],
        )
        payload["wav_roots"] = list(dict.fromkeys(str(root) for batch in batches for root in batch.output_roots))
        if payload["wav_roots"]:
            payload["wav_root"] = payload["wav_roots"][0]
        if payload.get("report_path"):
            try:
                path = Path(payload["report_path"])
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                path.with_name("failures.jsonl").write_text(
                    "".join(
                        json.dumps(
                            {"source_path": item.source_path, "output_path": item.output_path, "error": item.error},
                            ensure_ascii=False,
                        )
                        + "\n"
                        for batch in batches
                        for item in batch.failures
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.error("WAV 事件汇总报告保存失败，保留已完成输出：{}", exc)
                payload["report_error"] = str(exc)
        payload["batches"] = batches
        return payload


def with_event_output(function):
    """直接调用时立即分类；CLI 与 GUI 提供会话时等待本轮映射完成。"""

    @wraps(function)
    def run(*, ctx, version, wav_output, **kwargs):
        if not wav_output.group_by_event:
            return function(ctx=ctx, version=version, wav_output=wav_output, **kwargs)
        session = ctx.runtime_cache.get(EVENT_SESSION_KEY)
        if session is not None:
            session.tree_payload = {"wav_root": str(ctx.version_path("wav_event", version))}
            try:
                payload = function(ctx=ctx, version=version, wav_output=wav_output, **kwargs)
            except Exception as exc:
                session.tree_payload["errors"] = [str(exc)]
                raise
            payload["pending_event_output"] = True
            session.tree_payload = {key: value for key, value in payload.items() if key != "batches"}
            return payload
        with EventOutput(
            audio_root=ctx.version_path("audio", version),
            hash_root=ctx.version_path("hash", version),
            version=version,
            scratch_root=ctx.paths.temp_path,
        ) as session:
            ctx.runtime_cache[EVENT_SESSION_KEY] = session
            try:
                try:
                    run(ctx=ctx, version=version, wav_output=wav_output, **kwargs)
                except (OSError, ValueError, RuntimeError):
                    if not session.has_pending:
                        raise
                    # 后续目录失败不能丢弃先前已经完成的暂存音频。
                    logger.exception("WAV 目录执行中断，继续交付已完成批次")
                return session.finish_tree()
            finally:
                ctx.runtime_cache.pop(EVENT_SESSION_KEY, None)

    return run
