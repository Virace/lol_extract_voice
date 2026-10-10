# 本地游戏目录

可以使用已安装的英雄联盟客户端，也可以用外部工具单独获取资源并整理为本地目录。
程序按同一套规则读取这两种输入，无需选择来源模式。

## 需要哪些文件

游戏目录应指向下面的根目录：

```text
<游戏目录>/
├─ Game/
│  ├─ content-metadata.json
│  └─ DATA/FINAL/
│     └─ <所需的 .wad.client>
└─ LeagueClient/Plugins/rcp-be-lol-game-data/
   ├─ description.json
   └─ <description.json 引用的 LCU 资源>
```

| 文件 | 用途 |
| --- | --- |
| `Game/content-metadata.json` | 客户端版本信息 |
| `Game/DATA/FINAL/*.wad.client` | 所选英雄、地图和语言的实际资源 |
| `description.json` 及其引用的 LCU 资源 | 英雄、地图名单和语言等基础数据 |

> **需要真实、完整的资源。** 只建文件夹或只下载几个 WAD 不够；GAME 与 LCU 文件应属于同一版本。
> 外部准备目录无需包含 `LeagueClient.exe`。

## 如何使用

**界面：** 在“全局设置”中将游戏目录设为这个根目录，选择已有资源的语言，再创建任务。

**控制台：** 用 `--game-path` 指定这个根目录，命令示例见 [控制台使用说明](../cli-package.md)。

## 资源不完整时怎么办

| 情况 | 处理方法 |
| --- | --- |
| 找不到基础名单或版本信息 | 补齐上述 JSON 与 LCU 资源，确认目录可读取 |
| 缺少某个对象或语言的 WAD | 补齐任务所选对象与语言的资源后重试 |
| GAME 与 LCU 版本不一致 | 重新准备同一版本的整套资源 |
| 文件存在但解析失败 | 检查获取过程是否完整，保留错误提示和日志 |

`update` 准备的是应用所需的数据，不会补下载缺失的游戏文件。

外部准备工具作者和维护者请查看 [本地数据源验证合同](../development/prepared-source-contract.md)，
其中保留文件格式、验证阶段、共享资源与旧远程配置迁移的完整约定。
