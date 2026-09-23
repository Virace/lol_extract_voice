"""冻结控制台入口，先分流多进程，再运行 CLI。"""

import multiprocessing
import sys

if __name__ == "__main__":
    # 子进程内部参数不能进入业务参数解析，也不能重复初始化主任务。
    multiprocessing.freeze_support()

    if "--check-tools" in sys.argv:
        from lol_audio_unpack.runtime.probe_command import check_tools

        raise SystemExit(check_tools(sys.argv[1:]))

    from lol_audio_unpack.cli.cli import main

    raise SystemExit(main())
