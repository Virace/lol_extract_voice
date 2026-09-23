"""行为测试共用的完整应用上下文和有效音频样本。"""

import wave
from dataclasses import fields
from io import BytesIO
from pathlib import Path

from lol_audio_unpack.app.outputs import save_outputs
from lol_audio_unpack.app.types import AppConfig, AppContext, AppPaths
from lol_audio_unpack.runtime.library import Library, MediaRef
from lol_audio_unpack.unpack.entity import generate_output_path


def make_context(root: Path, *, config=None, paths=None, runtime_cache=None, **settings) -> AppContext:
    """将测试显式配置装配成真实上下文，不替换项目路径规则。"""
    config_values = vars(config).copy() if config is not None else {}
    path_values = vars(paths).copy() if paths is not None else {}
    config_names = {item.name for item in fields(AppConfig)}
    for key, value in settings.items():
        (config_values if key in config_names else path_values)[key] = value
    root = Path(path_values.get("audio_path", path_values.get("manifest_path", root / "audios"))).parent
    config_values.setdefault("output_path", root)
    config_values.setdefault("game_path", root / "game")
    roots = {"audio": "audios", "wav": "wavs", "hash": "hashes", "report": "reports", "log": "logs"}
    for item in fields(AppPaths):
        stem = item.name.removesuffix("_path")
        path_values.setdefault(item.name, root / roots.get(stem, stem))
    return AppContext(AppConfig(**config_values), AppPaths(**path_values), runtime_cache or {})


def make_wav() -> bytes:
    """生成可被完整解码的短 PCM 样本，避免把伪 WAV 当成成功产物。"""
    stream = BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\x01\x00" * 80)
    return stream.getvalue()


def make_library_view(ctx, entity, version, *, sub_id="1000", audio_type="VO", media_id=101, data=b"audio"):  # noqa: PLR0913
    """为定位测试建立真实对象、精确引用与链接，不使用无索引目录代替库。"""
    sub_id = str(entity.entity_id) if entity.entity_type != "champion" else sub_id

    with Library(ctx.config.output_path) as library:
        ref = MediaRef(
            entity.entity_type,
            str(entity.entity_id),
            media_id,
            library.publish(data).ref,
            sub_id if entity.entity_type == "champion" else None,
        )
        target = (
            generate_output_path(entity, sub_id, audio_type, ctx.version_path("audio", version), ctx=ctx)
            / f"{media_id}.wem"
        )
        path = target.relative_to(library.root)
        library.materialize(ref.object, path.as_posix())
        library.merge(version, ctx.game_region, [ref])
        save_outputs(library.root, version, ctx.game_region, entity.entity_type, str(entity.entity_id), [target])
    return ref, library.resolve(path.as_posix())


def publish_media(ctx: AppContext, entity, bank, version: str, media_id: int, data: bytes) -> MediaRef:  # noqa: PLR0913, PLR0917
    """以真实发布接口准备实体媒体引用，供消费者集成测试读取。"""
    ref, _path = make_library_view(
        ctx, entity, version, sub_id=bank.sub_id, audio_type=bank.audio_type, media_id=media_id, data=data
    )
    return ref
