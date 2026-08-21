# 解包与映射 API（核心流水线）

## 0. 本地 resource binding artifact

`local_path` 模式的 `update` 会对 declared BIN 与其引用的 BNK/WPK 做目标 hash 查询，
只扫描 `Game/DATA/FINAL` 下 root WAD 与当前 `game_region` 的 WAD TOC。命中位置写入
`manifest/<version>/banks/**`，不会持久化本机绝对路径。

本地 banks artifact 的资源合同版本位于顶层：

```yaml
resourceSchemaVersion: 2
entity:
  type: champion
  id: "60009"
binBindings:
  - path: data/characters/jade_fiddlesticks/skins/skin301.bin
    normalizedPath: data/characters/jade_fiddlesticks/skins/skin301.bin
    wad: Game/DATA/FINAL/Champions/FiddleSticks.wad.client
    entryHash: "0000000000000000"
    status: resolved
bankBindings:
  - category: Characters/Jade_Fiddlesticks/Skins/Skin301/VO
    path: assets/sounds/wwise2016/vo/example_audio.bnk
    normalizedPath: assets/sounds/wwise2016/vo/example_audio.bnk
    kind: BNK
    wad: Game/DATA/FINAL/Champions/FiddleSticks.zh_CN.wad.client
    entryHash: "0000000000000000"
    sourceBin: data/characters/jade_fiddlesticks/skins/skin301.bin
    role: localized
    status: resolved
diagnostics:
  completeness: complete
  unresolvedBins: []
  unresolvedBanks: []
```

单条解析状态为 `resolved`、`missing`、`ambiguous_identical`、
`ambiguous_conflict` 或 `parse_failed`。`diagnostics.completeness` 为
`complete`、`partial` 或 `failed`。同 hash 多候选只在歧义时读取 payload；内容不同不会
静默选择首项。

`DataReader.get_champion_banks(...)` 与 `get_map_banks(...)` 默认仍可读取旧 artifact；
需要精确 binding 的调用方传入 `require_bindings=True`，或使用
`get_champion_resource_bindings(...)` / `get_map_resource_bindings(...)`。旧 local artifact
会提示重新运行 `update`；`remote_snapshot` 继续使用既有 `.use_local_bin` 与 v1 投影，
不会实例化本地 WAD 索引。

`AudioEntityData` 在 local v2 会把每条 `BankBinding` 投影为 `AudioBank`：它只补充
逻辑子实体 ID 与音频类型，保留原始 binding 作为唯一物理资源事实。旧 local artifact 在
创建解包或 mapping 实体时会明确提示重新运行 `update`；不会退回 alias、分类名或旧投影猜测
WAD。`remote_snapshot` 仍保留 v1 root/language 投影，`resource_banks` 为空且
`binding_diagnostics` 为 `None`，不会创建本地 WAD index。

数据关系固定为：

```text
logical entity -> declared BIN -> BinBinding -> BANK_UNITS path
               -> BankBinding -> physical BNK/WPK -> original WEM + exact output path
```

一个 logical entity 可以跨多个 root/current-language WAD，因此消费者必须按 binding 的
`wad + entryHash` 处理，不能把 alias 还原为单一 WAD。地图更新仍先处理 Map 0 Common，
再对 Map 11/22 等目标去重；只有目标地图而没有 Map 0 的系统结果不构成有效验收。

### 0.1 显式 resource-pack 发现 artifact

本地 API 可在 `OperationOptions.resource_pack_wads` 传入由
`ResourcePackWadRef.from_path(game_root, path)` 创建的显式选择。每个 ref 只持久化游戏根相对
WAD identity 与 `st_size` / `st_mtime_ns`；选择和执行阶段均严格解析、确认仍在
`Game/DATA/FINAL` 下且为 `.wad.client`。remote 模式在应用门面拒绝该能力。

发现只打开 selected WAD 的 TOC，只读取 storage type 为 `0`、`1` 或 `3` 的非零 candidate。解压前
强制单 WAD 上限：4096 个 candidate、单 entry 4 MiB 未压缩尺寸、64 MiB candidate 压缩字节。候选
payload 必须以 `PROP` 开头才交给 BIN parser；其他 false positive 只计读取成本。bank 的物理 WAD
仍由 P1 resolver 按已声明 hash 查询 root/current-language TOC；除既有 hash 歧义比较外，不读取未选
WAD payload。

每个成功 `BANK_UNITS.category` 生成稳定 string identity：

```text
resource_pack:<wad-component>:<namespace-component>
```

组件使用 NFKC、casefold 与 UTF-8 percent encoding；WAD 组件去除 `.wad.client`。banks 与 events
分别写入 `manifest/<version>/banks/resource_packs/` 与
`manifest/<version>/events/resource_packs/`，文件名对完整 key 再做 percent encoding，payload 仍保存原
stable key。banks 的 v2 `entity.type` 固定为 `resource_pack`，`entity.id` 为完整 key；`resourcePack`
字段保存相对 WAD identity、stat fingerprint、category 与按 logical bank path 合并的 source entry hashes。
同 key 指向不同规范化 WAD identity 或 source fingerprint 的既有 artifact 会标记 conflict，绝不覆盖。
Map 22 已声明的 BIN entry 会按当前 map data/v2 binding ownership 从 candidate 中排除；该判定不依赖
WAD 文件名前缀，同一 selected WAD 中不属于 Map 22 的独立 BIN 仍可继续发现。

同 selected WAD/category 的重复声明按 logical bank path 合并，events 也去重。单 candidate parse failure、
bank unresolved 或单 pack conflict 不阻断其他 category；`ResourcePackDiscoveryResult.scans` 提供每个
selected-WAD 的状态、payload reads、压缩/未压缩字节与失败原因。尚无可解析 BIN 或无 BANK_UNITS bank
path 时不生成伪 pack artifact。banks/events 写入后必须回读并匹配本次 payload；任一持久化校验失败时
该 pack 报告为 failed，不会把不可供后续 consumer 读取的结果显示为扫描成功。

`DataReader.get_resource_pack_banks(...)`、
`get_resource_pack_resource_bindings(...)` 与 `get_resource_pack_events(...)` 提供该 artifact 的稳定读取
边界。`AudioEntityData.from_resource_pack(...)` 把每个 pack 构造为唯一 logical sub-entity，并复用
local v2 binding consumer：extract 只读取已解析的物理 WAD/entry，mapping 复用 WAD/HIRC cache。
音频、raw hash、integrated hash 与 report 分别隔离到 `resource_packs` group；所有文件名使用完整 key
的 Windows-safe component，payload 内仍保留完整 key。raw mapping 使用 `resourcePacks` data key，
integrated mapping 使用 `data.resourcePack` 的稳定结构，并保留 namespace、WAD、events、audioPaths 与
mapping diagnostics。缺 events 或没有可映射事件时仍会写入诊断，不会否定已经 extract 的平铺 WEM。

## 1. 解包入口

公开包：`lol_audio_unpack.unpack`

### 1.1 单实体入口

```python
def unpack_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> EntityUnpackStats
```

```python
def unpack_champion(..., *, ctx: AppContext, ...) -> EntityUnpackStats
def unpack_map(..., *, ctx: AppContext, ...) -> EntityUnpackStats
def unpack_resource_pack(..., *, ctx: AppContext, ...) -> EntityUnpackStats
```

### 1.2 批量入口

```python
def unpack_all(
    reader: DataReader,
    max_workers: int = 4,
    include_champions: bool = True,
    include_maps: bool = True,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
    persisted_wem_callback: Callable[[Path], None] | None = None,
) -> StageResult
```

```python
def unpack_champions(..., *, ctx: AppContext, ...) -> StageResult
def unpack_maps(..., *, ctx: AppContext, ...) -> StageResult
def unpack_resource_packs(..., *, ctx: AppContext, ...) -> StageResult
```

批量入口的 `stage` 固定为 `extract`。每个任务产生一个按输入顺序排列的 `EntityResult`；
实体异常只使该实体 failed，并继续同批其他实体。既有 `EntityUnpackStats` 的 `warning` / `error`
分别映射为公共 `partial` / `failed`，不会因为函数没有抛异常就升级为成功。空任务是带说明的
success no-op；未知任务类型与批处理基础设施错误不会伪装成实体 partial。`EntityResult.artifacts`
只记录 WEM 持久化成功回调中确认的真实路径；partial 或落盘后发生异常的实体仍保留此前路径。

### 1.3 输出路径规则

```python
def generate_output_path(
    entity_data: AudioEntityData,
    sub_id: str,
    audio_type: str,
    base_path: Path | None = None,
    *,
    ctx: AppContext,
) -> Path
```

`generate_output_path(...)` 受 `ctx.config.group_by_type` 影响：

- `True`：优先按音频类型分层
- `False`：优先按实体目录分层

实体与子实体目录命名规则统一复用 `app/path_layout.py`。

### 1.4 解包过程

单实体解包主线：

1. local v2 按每条成功 binding 的物理 WAD identity 与 entry 提取原始 bank；同一逻辑实体内
   只复用相同 `(wad identity, entry hash)` 的 raw 数据，仍分别写回各自子实体和音频类型。
2. remote v1 继续按语言 WAD / 根 WAD 的兼容投影提取。
3. 解析 `BNK` / `WPK` 并输出原始 ID 命名的 `.wem`；同一最终相对输出路径只写入一次。
4. 记录旧报告字段，并为 local v2 追加 `bindingDiagnostics`（逐 binding、逐 WAD 与
   `complete` / `partial` / `failed`）；报告不写入绝对 WAD 路径。

若当前工作流启用了 WAV，则由独立 `WAV 转码` stage 直接消费当前版本的 `audios/<version>` 输出树，
再统一调用 `transcode_tree(...)` 生成镜像 WAV。

英雄解包在 `ctx.config.with_bp_vo` 启用时会额外处理大厅 BP 语音。

## 2. 映射入口

公开包：`lol_audio_unpack.mapping`

### 2.1 单实体入口

```python
def build_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: RuntimeCache | None = None,
    *,
    ctx: AppContext,
    persisted_mapping_callback: Callable[[Path], None] | None = None,
) -> dict[str, Any]
```

```python
def build_champion(..., *, ctx: AppContext, persisted_mapping_callback=None) -> dict[str, Any]
def build_map(..., *, ctx: AppContext, persisted_mapping_callback=None) -> dict[str, Any]
def build_resource_pack(..., *, ctx: AppContext, persisted_mapping_callback=None) -> dict[str, Any]
```

`persisted_mapping_callback` 仅在 raw mapping 或 integrated 文件实际写入后接收对应 `Path`；它是
向后兼容的观测钩子，四个单实体入口仍返回原有的 `dict[str, Any]`。

### 2.2 批量入口

```python
def execute_tasks(
    tasks: list[EntityTask],
    reader: DataReader,
    max_workers: int = 4,
    integrate_data: bool = False,
    *,
    ctx: AppContext,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> StageResult
```

```python
def build_all(..., *, ctx: AppContext) -> StageResult
def build_champions(..., *, ctx: AppContext) -> StageResult
def build_maps(..., *, ctx: AppContext) -> StageResult
def build_resource_packs(..., *, ctx: AppContext) -> StageResult
```

mapping 批量结果的 `stage` 固定为 `mapping`。单、多线程都保留输入顺序的实体结果；进度回调
仍按实际完成顺序发送。单实体构建异常会记录 failed 并继续，空任务为 success no-op。每个
`EntityResult.artifacts` 只包含实际写出的 mapping 或 integrated 路径；没有可写映射的成功实体
保持空 artifact，异常在写入之后发生时仍保留已经确认的路径。

### 2.3 整合入口

```python
def integrate_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    mapping_result: dict[str, Any],
) -> dict[str, Any]
```

当 `integrate_data=True` 时，映射结果会与实体原始 banks / events 数据整合后再写出。

### 2.4 `RuntimeCache`

`mapping.session.RuntimeCache` 提供映射阶段的运行时缓存：

- `wad_cache`
- `extract_cache`
- `hirc_cache`
- `cache_lock`

### 2.5 当前映射语义

local v2 映射只遍历成功 binding 中的 `_events.bnk`，并直接使用 binding 指向的 WAD；同一
分类/路径位于多个 WAD 时会分别处理并合并原有 `events: category -> event -> WEM ID[]` 结构。
remote v1 才继续按分类名选择语言 WAD / 根 WAD 的兼容分支。

映射输出额外包含：

- 子实体 sibling `audioPaths: category -> event -> relativePath[]`，仅指向实际解包的 WEM；
  relative path 相对于当前逻辑实体输出根，使用 POSIX 分隔符，保留同 ID 的多路径。
- 顶层 `mappingDiagnostics`：映射完整度、路径级 WEM 覆盖、缺 events、未解析 bank 与错误分类。

没有 events 不会伪造 mapping 或让已解包 WEM 失败，而是产生可观察的 `partial` 诊断。
映射的本地 BNK/HIRC 磁盘缓存以完整 SHA-256 WAD identity namespace 隔离；运行期 key 同时
包含 WAD identity、规范化 bank path 和 HIRC backend。写入 cache 前会校验规范化 bank path
不能越出当前 WAD namespace；同 key 的并发提取在一次原子临界区内完成。events 中存在但没有
对应 binding 的分类会以 `status: missing` 写入 `unresolvedBankCategories`。

## 3. 编排层入口

`lol_audio_unpack.app.LolAudioUnpackApp` 负责把 update / extract / wav / mapping 串成完整工作流。

常用方法：

- `update(opts, *, target="all")`
- `extract(opts, *, include_champions=True, include_maps=True, prepare_remote=True, ...)`
- `transcode_wav(opts, *, progress_callback=None, job_label=None)`
- `mapping(opts, *, include_champions=True, include_maps=True, prepare_remote=True, ...)`
- `build_work_items(...)`
- `run_workflow(...)`
- `cleanup_remote_artifacts()`

`update(...)`、`extract(...)`、`transcode_wav(...)` 与 `mapping(...)` 都返回 `StageResult`；
`run_workflow(...)` 返回 `RunResult`。公共结果模型从 `lol_audio_unpack.app` 导出：

- `ResultStatus`：`success`、`partial`、`failed`、`cancelled`
- `EntityResult`：稳定实体 identity、状态、错误摘要与可选 artifact paths
- `StageResult`：阶段 key、实体结果、阶段错误与派生计数
- `RunResult`：按执行顺序保存阶段，并派生整轮状态

WAV runtime 实际处理至少一个文件时，`transcode_wav(...)` 会返回一个稳定的 `wav:batch`
实体，其 `artifacts` 为 runtime 报告的真实 `wav_root`；零文件 success no-op 不创建实体。
extract 的 artifacts 是本轮确认落盘的 WEM 或大厅音频路径，mapping 的 artifacts 是最终写入文件；
即使实体随后失败，已落盘路径仍会保留，供调用方进行有界刷新或恢复判断。

合法 no-op 是计数为 0 的 success。实体成功与失败并存时为 partial；全部失败为 failed；
cancelled 在整轮聚合中优先。完整 traceback 只写日志，不进入公共结果。
已知共享数据、下载与持久化异常会在 facade 阶段边界结果化；参数/合同 `ValueError` 与未声明为
可恢复的编程错误仍可能直接抛出，调用方不能把 typed result 理解为“任何异常都不会传播”。

## 4. remote 模式执行顺序

在 `remote_snapshot` 模式下，按实体拆批执行的主线是：

1. 可选先执行一次全局 `update`
2. 通过 `build_work_items(...)` 构建实体工作项队列
3. 单实体依次准备所需 WAD
4. 执行 `extract`
5. 执行 `mapping`
6. 清理当前实体远端产物

目标是降低磁盘峰值，而不是把 `extract + mapping` 合并成一个大步骤。
单实体重试耗尽会写入 failed `EntityResult` 并继续后续实体；清理失败作为独立 `cleanup`
阶段追加，不覆盖原始失败。实体完成回调只从 `EntityResult.artifacts` 解析本轮真实存在的路径；
预先存在的旧输出目录不是证据。partial 只有仍有这种落盘证据时才会触发完成回调。

## 5. 上下文约束

- `DataReader` 构造必须传入 `ctx: AppContext`；每次构造都是独立实例，不跨 context 共享 cache
- `LolAudioUnpackApp` 在单一 app/context 内懒加载复用 reader，并在 data、banks/events 或
  resource-pack artifact 的写入边界后异常安全地整体失效
- remote orchestrator 复用所属 app 的 reader；不同 app/context 不建立进程级共享 registry
- `AudioEntityData.from_champion/from_map` 必须传入 `ctx`
- 解包、映射、remote 准备相关主函数都要求显式上下文
