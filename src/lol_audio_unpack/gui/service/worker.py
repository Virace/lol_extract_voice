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
        print(f"=== DataLoadWorker.run 开始: {self.entity_type} ===")
        logger.info(f"开始加载 {self.entity_type} 数据")
        try:
            loader = EntityDataLoader(self.app_context)
            print(f"=== EntityDataLoader 创建成功 ===")
            data = loader.load_entities(self.entity_type)
            print(f"=== {self.entity_type} 数据加载成功，共 {len(data)} 条 ===")
            logger.info(f"{self.entity_type} 数据加载成功，共 {len(data)} 条")
            self.finished.emit(data)
            print(f"=== finished 信号已发送 ===")
        except Exception as e:
            print(f"=== {self.entity_type} 数据加载失败: {e} ===")
            logger.error(f"{self.entity_type} 数据加载失败: {e}", exc_info=True)
            self.error.emit(str(e))
