"""项目内复用的类型别名。"""

from os import PathLike
from typing import TypeAlias

StrPath: TypeAlias = str | PathLike[str]
