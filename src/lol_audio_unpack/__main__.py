"""lol_audio_unpack 的默认命令行入口薄壳。"""

from __future__ import annotations

from .cli.cli import main

__all__ = ["main"]


if __name__ == "__main__":
    main()
