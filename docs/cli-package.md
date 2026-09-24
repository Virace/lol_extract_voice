# Windows 控制台独立包

`LolAudioUnpack-CLI.exe` 是 Windows x64 控制台程序。在 PowerShell、CMD 或脚本中运行即可，
数据准备、解包、事件映射和内置 WAV 转码都不需要另外安装 Python、uv 或 Qt。

## 使用

```powershell
.\LolAudioUnpack-CLI.exe --help
.\LolAudioUnpack-CLI.exe --version
# 一条命令完成数据准备、解包、WAV 转码和事件映射
.\LolAudioUnpack-CLI.exe update extract wav mapping --champions Annie --game-path "<本地客户端目录>"
.\LolAudioUnpack-CLI.exe -c .\任务.ini
```

动作和参数与仓库里的 CLI 相同。生成映射时，使用 `LolAudioUnpack-CLI.exe mapping ...` 即可。

## 主流程：准备、解包、转码、映射

| 动作 | 用途 | 产物 |
| --- | --- | --- |
| `update` | 从本地客户端准备指定英雄或地图的资料、资源绑定和事件名 | `manifest/<版本>/<语言>/` |
| `extract` | 解包指定实体的原始 WEM，保留音频 ID | `audios/<版本>/<语言>/` |
| `wav` | 将所选实体已解包的音频批量转为 WAV | `wavs/<版本>/<语言>/` |
| `mapping` | 解析事件与 WEM 音频 ID 的对应关系 | `hashes/<版本>/<语言>/` |

这四个动作可以单独运行，也可以按需要组合在同一条命令中，共享英雄或地图选择。
实际执行顺序固定为 `update → extract → wav → mapping`，与动作书写顺序无关；已有前置数据时可省略对应动作。
只有 `export-json`（导出 JSON）和 `convert-wem`（指定文件转码）是不能加入主流程的独立命令。

例如，一条命令提取安妮和提莫的语音与技能音效，并直接生成 WAV：

```powershell
.\LolAudioUnpack-CLI.exe update extract wav --champions "Annie,Teemo" --exclude-type MUSIC --game-path "D:/Games/英雄联盟" --output-path .\output

# 同时需要事件映射时，加上 mapping
.\LolAudioUnpack-CLI.exe update extract wav mapping --champions "Annie,Teemo" --exclude-type MUSIC --game-path "D:/Games/英雄联盟" --output-path .\output
```

生成的 WAV 位于 `output/wavs/<版本>/<语言>/`。不必另外运行 `convert-wem`。
单独运行 `wav` 仅适用于对应实体已经解包、现在只需补做转码的情况。

首次处理实体先执行 `update`。查询事件对应哪些音频，要执行 `mapping`；它可以与 `update`
组合，在尚未解包 WEM 时运行。只需要部分 WAV 时，先查映射，再 `extract`，最后使用下面的
`convert-wem` 转码所选文件，避免全量转码。

```powershell
# 先准备常规公共资源并建立映射，不转码、不解包全量 WEM
.\LolAudioUnpack-CLI.exe update mapping --maps 0 --exclude-type VO,MUSIC --game-path "D:/Games/英雄联盟"

# 把地图 0 的已有映射导出为 JSON
.\LolAudioUnpack-CLI.exe export-json --maps 0 --json-output .\common.json

# 查到所需事件后，解包同一实体的 WEM
.\LolAudioUnpack-CLI.exe extract --maps 0 --exclude-type VO,MUSIC --game-path "D:/Games/英雄联盟"
```

英雄同时需要语音和技能音效时，可用 `--exclude-type MUSIC`；英雄选择示例为
`--champions "Annie,Teemo"`，数字 ID 为 `--champions "1,17"`。
若希望先查映射再解包，按上述示例分次执行。

## 导出映射 JSON

`export-json` 只读取已有映射，不要求提供 MSGPACK 路径或游戏目录；每次指定一个英雄或地图 ID。

```powershell
.\LolAudioUnpack-CLI.exe export-json --champions 1 --json-output .\annie.json
.\LolAudioUnpack-CLI.exe export-json --maps 0 --output-path .\output --game-version 16.19 --game-region zh_CN
```

- `--output-path` 是主流程输出根，默认 `./output`。它不是 JSON 的目标路径。
- `--json-output` 指定 `.json` 目标文件；省略时完整 JSON 写入标准输出，诊断写入标准错误。
- `--game-region` 默认 `zh_CN`。同一实体只有一个匹配版本时自动定位；多版本时列出版本，要求用
  `--game-version` 明确选择。普通和整合映射同时存在时选择最近生成的一份，同时间优先整合版。
- 原映射文件保留，JSON 不裁剪字段、不筛选事件。JSON 对象中的整数键表示为字符串。
- 映射缺失时提示先执行 `update mapping`，不会隐式更新或下载资源。

整合映射的英雄事件位于 `data.skins[].events.<类别>.mapping`，地图事件位于
`data.map.events.<类别>.mapping`；值为对应 WEM ID 列表。普通映射在 `skins` 或 `map` 中按
子实体和类别组织事件。每个事件可能对应多个 WEM，多个事件也可能引用同一音频。

若生成 mapping 时已经解包，对应节点可能还包含 `audioPaths` 精确相对路径；先 mapping 后 extract
时可能只有 ID。此时在当前版本、语言和实体的 `audios` 目录中按 `<WEM ID>.wem` 定位，保留多个匹配，
不要把装备 ID 或事件哈希当作 WEM ID。需要更新精确路径时可在解包后再次运行 `mapping`。

## 独立 WEM 转 WAV

`convert-wem` 直接处理文件，不需要游戏目录、manifest 或实体 ID。它不能与 `update`、`extract`、
`mapping`、`wav` 放在同一条命令中，也不读取主流程 `-c` INI。

```powershell
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/200504484.wem" --output-path .\selected-wavs
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/a.wem" "D:/音频/b.wem" --output-path .\selected-wavs
.\LolAudioUnpack-CLI.exe convert-wem --input-list .\selected.txt --output-path .\selected-wavs --wav-workers 4 --wav-format pcm16
```

`selected.txt` 使用 UTF-8（可以带 BOM），每行一个 WEM 路径，允许空行和包围路径的双引号。
相对路径以清单所在目录为起点；命令行上的相对路径以当前终端目录为起点。不展开通配符。
`--input` 和 `--input-list` 可以同时提供，重复文件只处理一次。

默认输出到 `./output/wavs`，按输入文件的共同父目录保留子目录，避免不同目录中的同名 WEM 冲突。
可用 `--input-root` 固定镜像根目录，所有输入必须在这个目录内；重试或分批转换时使用同一个根可保持布局稳定。
未指定根且输入跨卷时，各卷依次处理，分别输出到 `volume-1`、`volume-2` 等子目录，每卷内部仍使用批量并发。
输入根、输出位置和报告路径会写入诊断。

它复用正常 WAV 批处理，支持 `--wav-workers`（默认 2）、`--wav-format`（默认 `pcm16`）、
`--wav-retries`（最多尝试次数，包含首次，默认 3）以及 `--wav-timeout`（外部后端单文件超时，默认 5 秒）。
可用 `--vgmstream-path` 指定外部后端；默认使用内置后端。已有 WAV 默认跳过，显式 `--overwrite` 才覆盖。
报告保存在目标目录的 `reports/`，退出码沿用下文约定。

## 查找线索与输出复用

装备音效主要从地图 `0`（Common／常规）的跨地图公共资源查找，例如 `ITEMS_Global`；
地图专属声音再查对应地图。装备事件名可能使用装备 ID，也可能使用英文内部名称或其片段。
例如 16.19 版本中，心之钢可搜 `3084`，中娅沙漏可搜 `Zhonyas`；标记、提示音可尝试搜索 `PING`。
事件名称是检索线索，仍需区分类别和触发场景，如英雄购买装备的语音与装备自身音效。

中文装备名称与 ID 可参考腾讯官网数据：
[装备资料 items.js](https://game.gtimg.cn/images/lol/act/img/js/items/items.js)。
同名装备可能存在不同模式的 ID，官网资料也可能与本地版本不同，最终以本地资源和映射为准。

现有输出目录可作为后续任务复用的数据和音频缓存：`manifest` 保存准备数据，`hashes` 保存映射，
`audios` 保存原始 WEM，`wavs` 保存转码结果，`cache` 等目录用于运行期复用。
保留这些目录可避免重复准备、解包或转码；删除后相应步骤需要重做。不要把唯一需要保留的导出结果一起删掉。

## 运行约定与诊断

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

## 给 AI Agent 的使用指引

先阅读本说明和对应命令的 `--help`。根据用户目标选择英雄或地图 ID，首次执行 `update mapping`，
再用 `export-json --champions <ID>` 或 `export-json --maps <ID>` 取得完整映射；不需要自行定位或解析 MSGPACK。
自行检索 JSON 中的事件名称、类别和 WEM ID，装备优先查地图 0，必要时结合装备资料确认搜索词。
查到目标后执行对应实体的 `extract`，按映射路径或 WEM ID 找到实际文件，将所选路径写入逐行文本清单，
交给独立 `convert-wem` 转码。需要所选实体的全部音频时，可用一条 `update extract wav` 命令直接生成 WAV，
同时需要事件映射则使用 `update extract wav mapping`；无需逐文件调用 `convert-wem`。
所有步骤使用一致的输出根、游戏版本和语言；检查退出码与报告，未找到匹配或信息不足时向用户说明并澄清。
已有输出可以复用，任务结束时告诉用户结果位置、保留哪些中间数据及删除后的影响，清理由用户决定。
