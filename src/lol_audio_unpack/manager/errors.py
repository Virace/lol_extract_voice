"""共享数据相关的语义化异常与统一分类工具。

CLI 报错与 GUI 自动准备判定都需要识别"共享数据尚未就绪、应先运行更新"这一类
错误。历史上 GUI 在多个消费点各自硬编码中文文案子串来判断，一旦文案改写，判定会
静默失效。本模块把语义异常类型与文案标记集中到一处，作为单一事实源：

- 业务层（manager/service）抛出语义异常，调用方可用 ``isinstance`` 稳健判定。
- 跨 Qt 信号边界后异常类型会退化为字符串（``Signal(str)``），此时回退到集中维护的
  文案子串匹配；同一组标记只在这里维护一份。
"""

from __future__ import annotations

# 同时用于异常消息和字符串边界判定的文案标记，集中维护避免多处漂移。
SHARED_DATA_NOT_READY_MARKERS: tuple[str, ...] = (
    "请先运行更新程序",
    "请立即运行数据更新程序",
    "核心数据文件",
    "数据版本与游戏版本严重不匹配",
    "resource schema v2",
)


class SharedDataNotReadyError(Exception):
    """共享数据尚未就绪：需先运行更新程序后才能读取实体数据。"""


class SharedDataMissingError(SharedDataNotReadyError, FileNotFoundError):
    """核心数据文件或 bank 数据集目录缺失。

    同时继承 ``FileNotFoundError`` 以兼容既有按 ``FileNotFoundError`` 捕获的调用方。
    """


class DataVersionMismatchError(SharedDataNotReadyError, ValueError):
    """数据文件版本与当前游戏版本严重不匹配。

    同时继承 ``ValueError`` 以兼容既有按 ``ValueError`` 捕获/断言的调用方。
    """


class ResourceSchemaMismatchError(SharedDataNotReadyError, ValueError):
    """本地 banks artifact 缺少当前资源绑定合同。"""


def is_shared_data_not_ready(error: Exception | str) -> bool:
    """判断错误是否属于"共享数据未就绪、应提示或自动运行更新"的预期分支。

    优先按语义异常类型判定（健壮、不受文案影响）；当只拿到字符串（如跨 Qt 信号边界
    传递的错误消息）或携带相同文案的普通异常时，回退到集中维护的子串匹配。

    Args:
        error: 异常对象或其字符串形式。

    Returns:
        属于"共享数据未就绪"预期分支时返回 ``True``。
    """
    if isinstance(error, SharedDataNotReadyError):
        return True
    text = str(error)
    return any(marker in text for marker in SHARED_DATA_NOT_READY_MARKERS)


__all__ = [
    "SHARED_DATA_NOT_READY_MARKERS",
    "DataVersionMismatchError",
    "ResourceSchemaMismatchError",
    "SharedDataMissingError",
    "SharedDataNotReadyError",
    "is_shared_data_not_ready",
]
