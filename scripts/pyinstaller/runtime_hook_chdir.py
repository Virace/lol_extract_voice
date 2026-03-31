"""PyInstaller 冻结态运行时 hook。

在业务代码执行前，将当前工作目录固定到可执行文件所在目录，
避免快捷方式、外部 cwd 或绝对路径启动时导致相对路径语义漂移。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    launch_root = Path(sys.executable).resolve().parent
    os.chdir(launch_root)
