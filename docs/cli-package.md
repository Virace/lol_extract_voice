# Windows 控制台独立包

`LolAudioUnpack-CLI.exe` 是 Windows x64 控制台程序。在 PowerShell、CMD 或脚本中运行即可，
数据准备、解包、事件映射和内置 WAV 转码都不需要另外安装 Python、uv 或 Qt。

## 使用

```powershell
.\LolAudioUnpack-CLI.exe --help
.\LolAudioUnpack-CLI.exe --version
.\LolAudioUnpack-CLI.exe update extract mapping --champions Annie --game-path "<本地客户端目录>"
.\LolAudioUnpack-CLI.exe wav --champions Annie --game-path "<本地客户端目录>"
.\LolAudioUnpack-CLI.exe -c .\任务.ini
```

动作和参数与仓库里的 CLI 相同。生成映射时，使用 `LolAudioUnpack-CLI.exe mapping ...` 即可。

- 当前终端目录是相对路径的起点，与 EXE 放置位置无关。默认输出为当前目录的 `output/`。
- `-c` 不带路径时读取当前目录的 `config/lol-audio-unpack.ini`；显式路径及 INI 内相对路径也相对于当前终端目录。
- 配置文件模式只接受配置文件路径，动作和其他选项全部从 INI 读取。
- 成功退出码为 `0`，失败 `1`，输入错误 `2`，部分完成 `3`，取消 `130`。PowerShell 使用 `$LASTEXITCODE` 判断结果。
- 帮助和日志重定向到文件或管道时统一使用 UTF-8；程序不等待额外按键退出。Ctrl+C 用于取消任务。
- 只读取已有客户端或按要求准备的本地资源目录，不下载客户端资源。
- 显式 `--wwiser-path` 需要准备 wwiser 和 PATH 中可用的 Python；显式 `--vgmstream-path` 需要准备相应外部工具。这些工具不包含在默认包内。

转码工具有问题时，可以运行下面的命令，把诊断结果保存到文件：

```powershell
.\LolAudioUnpack-CLI.exe --check-tools .\诊断\tools.json --check-cancel
```

这会检查内置工具能否正常工作，包括取消操作。游戏资源缺失或任务失败的原因，还需要结合任务日志查看。
