from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext

from lol_audio_unpack.gui.service.data_loader import EntityDataLoader


def _is_expected_shared_data_control_flow_error(error: Exception | str) -> bool:
    """判断共享数据加载异常是否属于预期的自动准备分支。"""
    normalized = str(error)
    return (
        "请先运行更新程序" in normalized
        or "请立即运行数据更新程序" in normalized
        or "核心数据文件" in normalized
        or "数据版本与游戏版本严重不匹配" in normalized
    )


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
            logger.debug(f"{self.entity_type} 实体状态扫描完成，整理出 {len(data)} 个列表项")
            self.finished.emit(data)
            logger.debug(f"finished 信号已发送: {self.entity_type}")
        except Exception as e:
            if _is_expected_shared_data_control_flow_error(e):
                logger.info(f"{self.entity_type} 共享实体数据暂不可用，交由后续流程决定是否自动准备: {e}")
            else:
                logger.opt(exception=True).error(f"{self.entity_type} 实体扫描失败: {e}")
            self.error.emit(str(e))


