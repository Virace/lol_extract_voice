# 已准备本地数据源合同（Prepared Game Source Contract v1）

Lol Audio Unpack 只从 `game_path` 指向的本地文件系统读取游戏资源。这个目录既可以是已安装的
英雄联盟客户端，也可以由独立工具提前准备；两者使用同一套目录和资源校验，不需要选择来源模式。

本项目不负责下载客户端资源、解析远端清单或维护远端缓存。缺少本地文件时会直接报错，不会静默
访问网络或切换到其他来源。

## 1. 基础目录结构

`game_path` 至少需要提供以下结构：

```text
<game_path>/
├─ Game/
│  ├─ content-metadata.json
│  └─ DATA/
│     └─ FINAL/
│        └─ <目标需要的 .wad.client>
└─ LeagueClient/
   └─ Plugins/
      └─ rcp-be-lol-game-data/
         ├─ description.json
         └─ <description.json 引用的 LCU 资源>
```

共享预检要求：

- `game_path`、`Game/DATA/FINAL` 和 `LeagueClient/Plugins/rcp-be-lol-game-data` 是可读取目录。
- `Game/content-metadata.json` 是有效 JSON 对象，并包含非空字符串 `version`。
- `LeagueClient/Plugins/rcp-be-lol-game-data/description.json` 是有效 JSON 对象，并包含对象类型的
  `riotMeta`。
- `LeagueClient.exe` 不是合同的一部分，外部准备目录无需复制它。

基础预检只确认所有工作流共享的结构。`update` 仍会按英雄、地图、语言和事件范围验证
`description.json` 引用的 LCU 资源，以及目标所需的 GAME WAD、BIN、BNK/WPK。只复制目录骨架
不能替代这些实际资源。

## 2. 使用方式

已安装客户端与外部准备目录的调用方式完全相同：

```bash
uv run unpack update extract \
  --champions Annie,Ahri \
  --game-path "D:/Games/Tencent/WeGameApps/英雄联盟" \
  --output-path "./output"
```

```bash
uv run unpack update extract \
  --champions 1,103 \
  --game-path "D:/prepared/lol-client" \
  --output-path "./output"
```

Python 接入同样只设置 `GAME_PATH`：

```python
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions, create_app_context

ctx = create_app_context(
    settings={
        "GAME_PATH": "D:/prepared/lol-client",
        "OUTPUT_PATH": "./output",
        "GAME_REGION": "zh_CN",
    }
)
app = LolAudioUnpackApp(ctx)

update_result = app.update(OperationOptions(champion_ids=(1, 103)))
extract_result = app.extract(OperationOptions(champion_ids=(1, 103)), include_maps=False)
```

外部准备器应自行保证同一目录中的 GAME 与 LCU 数据版本匹配，并在交付目录前完成下载完整性
校验。本项目只验证消费所需的本地事实，不定义外部工具的网络、缓存或重试协议。

## 3. 验证阶段与失败边界

验证分为两层：

1. `create_app_context(...)` 执行共享基础预检。失败时抛出 `AppContextValidationError`，且发生在
   文件日志、manifest、音频、映射和报告等输出初始化之前。
2. `update` 为目标建立 resource schema v2 bindings。每条 binding 保存游戏根相对 WAD identity
   和 entry hash；解包与映射只消费成功 binding，不从 alias、分类名或历史标记猜测物理资源。

因此，基础预检通过只代表目录可以进入应用主链，不代表任意英雄或地图的全部资源都已准备。
目标资源缺失会在 update 或后续阶段以明确的 partial/failed 结果和诊断体现。

英雄 banks artifact 在首次生成或强制重新生成时附带 `skinAudio`，以皮肤 ID 为键，分别记录
`VO`、`SFX` 的 `independent`（独立资源）、`shared`（复用其他皮肤的物理资源）、
`absent`（BIN 已解析且未声明该类音频）、`unknown`（BIN 或资源未能确认）。共享通过 WAD
和 entry 的实际绑定判断；无声明不推断具体来源，也不等于资源丢失。该字段是 v2 的附加信息，
旧清单没有该字段时保持未知，可通过“重新生成实体数据”补齐。

映射会为指向相同物理 bank 的原皮肤共享分类复用已知事件；正常复用不再计为缺事件。
独立资源缺失、不同 bank 或解析失败仍保留不完整诊断。整合映射保留 `skinAudio`，
`mappingDiagnostics.sharedEventCategories` 列出本轮复用原皮肤事件的分类。

解包时，解析成功但没有内嵌 WEM 的 BNK 记录为 `no_audio`，正常跳过；音频可能由配套 WPK
提供。空字节、容器解析失败或有条目却没有可写音频仍属于错误。炫彩与普通皮肤均按清单中的
真实 ID、名称和 bindings 参与解包及整合映射，不因炫彩元数据嵌套在普通皮肤下而漏项。

GUI 终态按阶段列出结果，异常摘要保留对象和具体原因；不把同一英雄在多个阶段的处理次数
合并成一个“成功/部分成功”的对象计数。

## 4. 从旧远程模式迁移

旧配置中的以下项目已不再支持：

- `source_mode`
- `remote_live_region`
- `cleanup_remote`
- `remote_version`
- `remote_lcu_manifest_url`
- `remote_game_manifest_url`

INI 读取器会把这些项目视为未知配置并记录警告，然后忽略它们。请删除旧项目，并把已经准备好的
目录直接填写到 `game_path`。CLI 与 Python API 不再提供对应的远程参数、类型或工作流方法。

升级不会自动删除历史 `_prepared_game`、`cache/remote`、`manifest/<version>/bin_input` 或
`.use_local_bin`。如需释放空间，请在确认目录不再被其他工具使用后自行处理；当前版本不会读取
这些历史产物，也不会用它们覆盖本地 WAD 索引。
