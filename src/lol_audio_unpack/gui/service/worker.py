from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from lol_audio_unpack.app_context import AppContext

from lol_audio_unpack.gui.service.data_loader import EntityDataLoader


class DataLoadWorker(QThread):
    """异步数据加载线程"""

    finished = Signal(list)
    error = Signal(str)

    def __init__(self, app_context: AppContext, entity_type: str):
        super().__init__()
        self.app_context = app_context
        self.entity_type = entity_type

    def run(self):
        logger.debug(f"DataLoadWorker 线程启动: {self.entity_type}")
        try:
            loader = EntityDataLoader(self.app_context)
            logger.debug("EntityDataLoader 初始化成功")
            data = loader.load_entities(self.entity_type)
            logger.info(f"{self.entity_type} 数据加载成功，共 {len(data)} 条")
            self.finished.emit(data)
            logger.debug(f"finished 信号已发送: {self.entity_type}")
        except Exception as e:
            logger.error(f"{self.entity_type} 数据加载失败: {e}")
            self.error.emit(str(e))
