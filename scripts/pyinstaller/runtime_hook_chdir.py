"""PyInstaller 冻结态运行时 hook。

在业务代码执行前，将当前工作目录固定到可执行文件所在目录，
避免快捷方式、外部 cwd 或绝对路径启动时导致相对路径语义漂移。
"""

from lol_audio_unpack.utils.runtime_paths import apply_frozen_working_directory


apply_frozen_working_directory()
