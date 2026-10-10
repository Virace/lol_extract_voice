# 解包与映射 API（核心流水线）

## 0. 本地 resource binding artifact

`update` 会对 declared BIN 与其引用的 BNK/WPK 做目标 hash 查询，
只扫描 `Game/DATA/FINAL` 下 root WAD 与当前 `game_region` 的 WAD TOC。命中位置写入
`manifest/<version>/<region>/banks/**`，不会持久化本机绝对路径。

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

| 读取方式 | 约束 |
| --- | --- |
| `get_champion_banks(...)` / `get_map_banks(...)` | 默认可读旧 artifact，供迁移检查 |
| 读取物理资源 | 必须传入 `require_bindings=True`，或使用 `get_champion_resource_bindings(...)` / `get_map_resource_bindings(...)` |
| 旧 artifact | 提示重新 `update`；`.use_local_bin` 和 `manifest/<version>/bin_input` 不参与解析，也不绕过本地 WAD 索引 |

`AudioEntityData` 会把每条 v2 `BankBinding` 投影为 `AudioBank`：它只补充
逻辑子实体 ID 与音频类型，保留原始 binding 作为唯一物理资源事实。旧 local artifact 在
创建解包或 mapping 实体时会明确提示重新运行 `update`；不会退回 alias、分类名或旧投影猜测
WAD。

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
`ResourcePackWadRef.from_path(game_root, path)` 创建的显式选择。

- ref 只持久化游戏根相对 WAD identity 与 `st_size` / `st_mtime_ns`。
- 选择与执行阶段都严格解析路径，确认仍在 `Game/DATA/FINAL` 下且为 `.wad.client`。

#### 扫描范围与上限

| 检查 | 规则 |
| --- | --- |
| TOC | 仅打开 selected WAD，读取 storage type 为 `0`、`1`、`3` 的非零 candidate |
| 单 WAD candidate 数 | 最多 4096 |
| 单 entry 未压缩尺寸 | 最多 4 MiB |
| candidate 压缩字节总量 | 最多 64 MiB |
| BIN parser 输入 | payload 必须以 `PROP` 开头，其他 false positive 只计读取成本 |

以上上限在解压前执行。bank 的物理 WAD 仍由 P1 resolver 按声明 hash 查询 root/current-language TOC；
除既有 hash 歧义比较外，不读取未选 WAD payload。

每个成功 `BANK_UNITS.category` 生成稳定 string identity：

```text
resource_pack:<wad-component>:<namespace-component>
```

#### 身份与持久化

- 组件使用 NFKC、casefold、UTF-8 percent encoding，WAD 组件去除 `.wad.client`。
- banks/events 分别写入 `manifest/<version>/<region>/banks/resource_packs/` 与 `manifest/<version>/<region>/events/resource_packs/`。
- 文件名对完整 key 再做 percent encoding，payload 保留原 stable key；v2 `entity.type` 为 `resource_pack`，`entity.id` 为完整 key。
- `resourcePack` 保存相对 WAD identity、stat fingerprint、category，以及按 logical bank path 合并的 source entry hashes。
- 同 key 的既有 artifact 若指向不同规范化 WAD identity 或 source fingerprint，标记 conflict，不覆盖。
- Map 22 声明的 BIN entry 按 map data/v2 binding ownership 排除，不依赖文件名前缀；同一 selected WAD 中其他独立 BIN 仍可发现。

#### 失败与读取边界

- 同 selected WAD/category 的重复声明按 logical bank path 合并，events 去重。单 candidate parse failure、bank unresolved 或 pack conflict 不阻断其他 category。
- `ResourcePackDiscoveryResult.scans` 提供每个 selected-WAD 的状态、payload reads、压缩/未压缩字节与失败原因。
- 无可解析 BIN 或 BANK_UNITS bank path 时，不生成伪 artifact。banks/events 写入后必须回读匹配 payload；持久化校验失败时该 pack 为 failed。

| 消费边界 | 规则 |
| --- | --- |
| `DataReader` | 通过 `get_resource_pack_banks(...)`、`get_resource_pack_resource_bindings(...)`、`get_resource_pack_events(...)` 读取 |
| `AudioEntityData.from_resource_pack(...)` | 每个 pack 是唯一 logical sub-entity，复用 local v2 consumer；extract 只读已解析 WAD/entry，mapping 复用 WAD/HIRC cache |
| 文件与分组 | 音频、raw hash、integrated hash、report 隔离到 `resource_packs`；文件名为完整 key 的 Windows-safe component，payload 保留完整 key |
| 映射结构 | raw 使用 `resourcePacks`，integrated 使用 `data.resourcePack`；保留 namespace、WAD、events、audioPaths 与诊断 |
| 缺事件 | 写入诊断，不否定已 extract 的平铺 WEM |

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

| 批量解包结果 | 语义 |
| --- | --- |
| 阶段与顺序 | `stage = extract`，每个任务产生按输入顺序排列的 `EntityResult` |
| 单实体异常 | 该实体 failed，同批其他实体继续 |
| 统计映射 | `EntityUnpackStats.warning/error` 对应 `partial/failed`，不因未抛异常升级为成功 |
| 空任务 | 带说明的 success no-op |
| 基础设施错误 | 未知任务类型与批处理错误不伪装成实体 partial |
| `artifacts` | 只收录持久化成功回调确认的 WEM 路径；partial 或落盘后异常仍保留之前路径 |

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
2. 解析 `BNK` / `WPK`，以实际字节发布内容对象，再建立原始 ID 命名的可见 `.wem`；
   按实体、皮肤、音频类型与原 ID 汇总媒体，同目标路径采用本轮首次成功写入，成功引用并入版本/区域单索引。
3. 记录兼容报告字段，并追加 `bindingDiagnostics`（逐 binding、逐 WAD 与
   `complete` / `partial` / `failed`）；报告不写入绝对 WAD 路径。

若当前工作流启用了 WAV，则由独立 `WAV 转码` stage 消费当前版本/语言的 `audios/<version>/<region>` 输出树，
按内容、输出参数和后端构建复用完整 WAV，需要转换的内容再通过共用批处理生成镜像输出。

LCU 基础数据更新默认同时预取选人语音、禁用语音和选人音效到 `manifest` 缓存。
英雄解包时才将对应文件硬链接到英雄的 `lobby/`，缓存缺失时按英雄补齐；三种文件不受
VO/SFX 筛选影响，也不进入 WEM 内容库。`ctx.config.lobby_audio=False` 可关闭大厅音频。

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

| 批量映射结果 | 语义 |
| --- | --- |
| `stage` | 固定为 `mapping` |
| 顺序 | 单、多线程都按输入顺序保存实体结果，进度按实际完成顺序发送 |
| 异常与空任务 | 单实体构建异常记 failed 并继续，空任务为 success no-op |
| `EntityResult.artifacts` | 仅含实际写出的 mapping/integrated 路径；无可写映射的成功实体为空，写入后异常仍保留已确认路径 |

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

映射只遍历成功的 v2 binding 中的 `_events.bnk`，并直接使用 binding 指向的 WAD；同一
分类/路径位于多个 WAD 时会分别处理并合并原有 `events: category -> event -> WEM ID[]` 结构。

映射输出额外包含：

- 子实体 sibling `audioPaths: category -> event -> relativePath[]`，仅指向实际解包的 WEM；
  relative path 相对于当前逻辑实体输出根，使用 POSIX 分隔符，保留同 ID 的多路径。
- 顶层 `mappingDiagnostics`：映射完整度、路径级 WEM 覆盖、缺 events、未解析 bank 与错误分类。

没有 events 不会伪造 mapping 或让已解包 WEM 失败，而是产生可观察的 `partial` 诊断。

| 映射缓存与诊断 | 规则 |
| --- | --- |
| 磁盘 namespace | 本地 BNK/HIRC 按完整 SHA-256 WAD identity 隔离 |
| 运行期 key | 包含 WAD identity、规范化 bank path、HIRC backend |
| 写入边界 | 校验 bank path 不越出当前 namespace，同 key 并发提取在一次原子临界区完成 |
| 无 binding 分类 | events 中的该分类以 `status: missing` 写入 `unresolvedBankCategories` |

## 3. 编排层入口

`lol_audio_unpack.app.LolAudioUnpackApp` 负责把 update / extract / wav / mapping 串成完整工作流。

常用方法：

- `update(opts, *, target="all", progress_callback=None)`
- `discover_resource_packs(opts)`
- `extract(opts, *, include_champions=True, include_maps=True, progress_callback=None, persisted_wem_callback=None)`
- `transcode_wav(opts, *, progress_callback=None, job_label=None)`
- `mapping(opts, *, include_champions=True, include_maps=True, progress_callback=None)`
- `prepare_update_data(*, force_update=False)`
- `resolve_champion_ids(selectors)`

`update(...)`、`extract(...)`、`transcode_wav(...)` 与 `mapping(...)` 都返回 `StageResult`。
控制台与界面可以按执行顺序把这些阶段聚合为 `RunResult`。公共结果模型从
`lol_audio_unpack.app` 导出：

- `ResultStatus`：`success`、`partial`、`failed`、`cancelled`
- `EntityResult`：稳定实体 identity、状态、错误摘要与可选 artifact paths
- `StageResult`：阶段 key、实体结果、阶段错误与派生计数
- `RunResult`：按执行顺序保存阶段，并派生整轮状态

`update(...)` 的可选 `progress_callback` 接收 `OperationProgress`，目前覆盖 `data`、
`champion_banks` 与 `map_banks` 阶段。进度只描述阶段内处理位置；即使 current 到达 total，调用方
仍必须以最终 `StageResult` 判断成功、部分完成、失败或取消。

`OperationOptions.process_events=False` 时，events artifact 的缺失或新鲜度不参与逐实体更新判定；
只要 banks 已就绪即可跳过 BIN 读取。启用事件处理时也只在 events 缺失、过期或显式 force 时提取
事件；banks 单独因 resource schema 迁移需要重建时，不会重复解析已经新鲜的 events。

| 阶段产物 | `artifacts` 内容 |
| --- | --- |
| WAV 有生成或复用结果 | 稳定 `wav:batch` 实体指向 runtime 报告的真实 `wav_root`；零文件 success no-op 不创建实体 |
| extract | 本轮确认落盘的 WEM 或大厅音频路径 |
| mapping | 最终写入的文件 |

实体随后失败仍保留已落盘路径，供调用方进行有界刷新或恢复判断。

### 3.1 WAV 输出与结果

| 项目 | 语义 |
| --- | --- |
| 共用入口 | 目录、所选范围与单文件导出使用 `runtime.wav.batch.run_batch` |
| 普通导出 | 默认跳过同名目标，界面可显式覆盖 |
| 库内复用 | 核对输入摘要、当前采样格式与目标存在性；格式变化替换固定输出，不保存历史方案 |
| `StageResult.wav_batches` | 保存输出成功、实际转换、复用、失败、冲突跳过计数，以及精确失败输入和独立报告地址 |
| `reports` | 本轮报告路径；报告写入失败时仍保留内存 typed result |

### 3.2 文件重试

- 内外后端共用文件任务级重试，`max_retries` 是含首次的最大尝试次数，默认 3。
- 仅重试有可靠身份的失败文件：重做读取、转码、校验与落盘，保持后端和参数；成功文件不重跑，工具预检只执行一次。
- 预检失败或缺少可靠文件终态的批处理异常，不伪造逐项失败重试。
- 次数耗尽仍保留精确失败项与最终诊断，报告不因重试重复累计文件。
- 解包 `EntityResult.failures` 在身份可靠时区分文件与容器，容器失败不代表已知数量的音频失败。

### 3.3 状态与异常

| 状态 | 聚合语义 |
| --- | --- |
| 合法 no-op | 计数为 0 的 success |
| 成功与失败并存 | partial |
| 全部失败 | failed |
| cancelled | 整轮聚合中优先 |

完整 traceback 只进入日志。已知共享数据、持久化异常在 facade 阶段边界结果化；
参数/合同 `ValueError` 与未声明可恢复的编程错误仍可能抛出，typed result 不保证阻止所有异常传播。

## 4. 本地数据源执行顺序

真实客户端与外部准备目录共用以下主线：

1. `create_app_context(...)` 验证 `game_path` 的共享 GAME/LCU 结构。
2. 源任务先按所选语言与目标检查必需文件，再由 `update` 生成 v2 resource bindings 与 events。
3. `extract` 按 binding 指向的 WAD/entry 解包原始 WEM。
4. 可选执行独立 WAV stage。
5. `mapping` 按同一 binding 和 events 生成映射。

基础结构验证与所选目标文件预检分开：后者阻止缺必需 WAD 的任务，但不解析或校验其内容。
BIN 或 bank 的解析错误由对应消费者按目标报告；旧输出目录不能替代本轮 `EntityResult.artifacts` 成为成功证据。完整目录
合同见 [已准备本地数据源合同](./prepared_source.md)。

## 5. 上下文约束

- `DataReader` 构造必须传入 `ctx: AppContext`；每次构造都是独立实例，不跨 context 共享 cache
- `LolAudioUnpackApp` 在单一 app/context 内懒加载复用 reader，并在 data、banks/events 或
  resource-pack artifact 的写入边界后异常安全地整体失效
- 不同 app/context 不建立进程级共享 reader registry
- `AudioEntityData.from_champion/from_map` 必须传入 `ctx`
- 解包与映射相关主函数都要求显式上下文
