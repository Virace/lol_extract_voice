# Windows 控制台独立包

`LolAudioUnpack-CLI.exe` 是 Windows x64 控制台程序，支持本地客户端的数据准备、音频解包、事件映射和 WAV 转码。
下文使用简写程序名，下载的文件名带版本号时请替换为实际名称。相对路径以当前终端目录为起点，默认输出到 `./output`。

## 动作与参数

| 动作 | 用途 | 输出目录 |
| --- | --- | --- |
| `update` | 准备英雄、地图资料及资源绑定、事件名 | `manifest/<版本>/<语言>/` |
| `extract` | 解包原始 WEM，保留音频 ID | `audios/<版本>/<语言>/` |
| `wav` | 将所选英雄或地图已解包的音频转为 WAV | `wavs/<版本>/<语言>/` |
| `mapping` | 建立事件名与 WEM ID 的对应关系 | `hashes/<版本>/<语言>/` |

四个动作可单独运行，也可组合使用，执行顺序固定为 `update → extract → wav → mapping`。
首次处理需要 `update`；`wav` 需要已有解包结果；`mapping` 可在解包前运行。
`export-json` 和 `convert-wem` 是独立命令，不能与这四个动作组合。

| 参数 | 说明 |
| --- | --- |
| `--game-path` | 本地游戏目录 |
| `--output-path` | 输出根目录，默认 `./output` |
| `--champions` | 英雄 ID 或英文别名，逗号分隔，如 `1,17` 或 `Annie,Teemo` |
| `--maps` | 地图 ID，逗号分隔；`0` 为常规公共资源 |
| `--exclude-type` | 排除的音频类型，如 `MUSIC` 或 `VO,MUSIC` |
| `--game-region` | 资源语言，默认 `zh_CN` |

英雄按整个实体处理，包含各皮肤的音频；共享资源由程序去重。WEM 和 WAV 按英雄、皮肤、音频类型分目录保存。

## 常用命令

```powershell
# 查看帮助和版本
.\LolAudioUnpack-CLI.exe --help
.\LolAudioUnpack-CLI.exe --version

# 提取安妮、提莫的全部音频，直接生成 WAV
.\LolAudioUnpack-CLI.exe update extract wav --champions Annie,Teemo --game-path "D:/Games/英雄联盟" --output-path .\output

# 提取英雄 VO/SFX，排除音乐，同时生成事件映射
.\LolAudioUnpack-CLI.exe update extract wav mapping --champions 1,17 --exclude-type MUSIC --game-path "D:/Games/英雄联盟"

# 只准备常规公共音效并生成映射，供事件查询使用
.\LolAudioUnpack-CLI.exe update mapping --maps 0 --exclude-type VO,MUSIC --game-path "D:/Games/英雄联盟"

# 解包常规公共音效并生成映射，保留 WEM，不转码
.\LolAudioUnpack-CLI.exe update extract mapping --maps 0 --exclude-type VO,MUSIC --game-path "D:/Games/英雄联盟"

# 将已解包的英雄音频转为 WAV
.\LolAudioUnpack-CLI.exe wav --champions Annie,Teemo --game-path "D:/Games/英雄联盟"

# 从配置文件读取动作和参数
.\LolAudioUnpack-CLI.exe -c .\任务.ini
```

`-c` 配置文件模式与命令行动作、参数互斥。省略配置路径时读取 `config/lol-audio-unpack.ini`。

## 导出映射 JSON

`export-json` 按英雄或地图 ID 查找已有映射，完整导出为 JSON。查询事件对应的音频 ID 需要先执行 `mapping`。

```powershell
.\LolAudioUnpack-CLI.exe export-json --maps 0 --json-output .\common.json
.\LolAudioUnpack-CLI.exe export-json --champions 1 --json-output .\annie.json
.\LolAudioUnpack-CLI.exe export-json --maps 0 --output-path .\output --game-version 16.19 --game-region zh_CN
```

每次指定一个英雄或地图 ID。`--output-path` 指向主流程输出根；`--json-output` 是 JSON 文件路径，省略时写入标准输出。
只有一个匹配版本时自动选择，多版本时用 `--game-version` 指定。普通和整合映射同时存在时选择最近生成的一份，同时间优先整合版。

整合映射的事件位于 `data.skins[].events.<类别>.mapping`（英雄）或 `data.map.events.<类别>.mapping`（地图），
值为 WEM ID 列表。普通映射在 `skins` 或 `map` 中按子实体和类别组织事件。
一个事件可能对应多个 WEM，多个事件也可能共用一个文件。已解包时映射可能包含 `audioPaths`；
只有 ID 时，可在对应版本、语言和实体的 `audios` 目录中按 `<WEM ID>.wem` 查找。

装备自身音效主要位于地图 `0` 的 `ITEMS_Global`，英雄与装备交互的台词属于英雄语音。
装备事件可能使用装备 ID 或英文内部名称，例如心之钢的 `3084`、中娅沙漏的 `Zhonyas`；标记提示音可搜索 `PING`。
英文前缀可能命中其他装备或模式变体，具体归属以完整事件名和本地资源为准。
中文装备名称与 ID 可参考腾讯的[装备资料 items.js](https://game.gtimg.cn/images/lol/act/img/js/items/items.js)，其版本可能与本地客户端不同。

## 独立 WEM 转码

`convert-wem` 接受单个文件、多个文件或文本清单，使用内置转码后端。它独立于英雄、地图和主流程配置。

```powershell
# 单个文件
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/200504484.wem" --output-path .\selected-wavs

# 多个文件
.\LolAudioUnpack-CLI.exe convert-wem --input "D:/音频/a.wem" "D:/音频/b.wem" --output-path .\selected-wavs

# 从清单批量转码，使用 4 个并发任务
.\LolAudioUnpack-CLI.exe convert-wem --input-list .\selected.txt --output-path .\selected-wavs --wav-workers 4 --wav-format pcm16
```

清单为 UTF-8 文本，每行一个 WEM 路径，支持 BOM、空行和包围路径的双引号。
清单内的相对路径以清单目录为起点，命令行路径以当前终端目录为起点；不展开通配符，重复文件只处理一次。

默认输出到 `./output/wavs`，按输入文件的共同父目录保留子目录。`--input-root` 可固定这个根目录；
未指定根且输入跨卷时，各卷分别输出到 `volume-1`、`volume-2` 等目录。
已有 WAV 默认跳过，`--overwrite` 可覆盖。报告保存在输出目录的 `reports/`。
并发、格式、重试和外部后端等参数见 `convert-wem --help`。

## 输出与诊断

`manifest`、`hashes`、`audios` 和 `cache` 可供后续任务复用，删除后相应步骤需要重做。最终 WAV 保存在 `wavs` 或指定的转码输出目录。
各步使用相同的输出根、版本和语言，才能复用同一批数据。

成功退出码为 `0`，失败 `1`，输入错误 `2`，部分完成 `3`，取消 `130`。PowerShell 可用 `$LASTEXITCODE` 查看。
日志位于输出根的 `logs/`，帮助和重定向输出使用 UTF-8。Ctrl+C 可取消任务。
程序只读取本地资源，不下载客户端文件。内置转码工具可通过以下命令检查：

```powershell
.\LolAudioUnpack-CLI.exe --check-tools .\诊断\tools.json --check-cancel
```

## 给 AI Agent 的提示

按用户要求选择动作：整实体音频可直接用 `update extract wav`，只有需要筛选事件时才查询映射并使用独立转码。
沿用工具默认的处理范围和输出结构，额外筛选、重命名或整理按用户要求进行。完成后简要告知结果位置和未完成项。
