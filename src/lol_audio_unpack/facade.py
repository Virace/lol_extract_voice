"""应用门面兼容层。

当前首选入口已迁移到 ``lol_audio_unpack.app.facade`` 与
``lol_audio_unpack.app.remote``。
本模块仅保留旧导入路径兼容，后续阶段会删除。
"""

from __future__ import annotations

from .app.facade import LolAudioUnpackApp
from .app.remote import RemoteEntityCallbackPayload, RemoteEntityWorkItem

__all__ = ["LolAudioUnpackApp", "RemoteEntityCallbackPayload", "RemoteEntityWorkItem"]
