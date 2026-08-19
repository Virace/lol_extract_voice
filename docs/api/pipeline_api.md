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
    wav_submitter: Callable[[Path], None] | None = None,
) -> None
```

```python
def unpack_champion(..., *, ctx: AppContext, ...) -> None
def unpack_map(..., *, ctx: AppContext, ...) -> None
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
    wav_output: WavOutputOptions | None = None,
) -> None
```

```python
def unpack_champions(..., *, ctx: AppContext, wav_output: WavOutputOptions | None = None) -> None
def unpack_maps(..., *, ctx: AppContext, wav_output: WavOutputOptions | None = None) -> None
```

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
) -> dict[str, Any]
```

```python
def build_champion(..., *, ctx: AppContext) -> dict[str, Any]
def build_map(..., *, ctx: AppContext) -> dict[str, Any]
```

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
) -> None
```

```python
def build_all(..., *, ctx: AppContext) -> None
def build_champions(..., *, ctx: AppContext) -> None
def build_maps(..., *, ctx: AppContext) -> None
```

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

## 4. remote 模式执行顺序

在 `remote_snapshot` 模式下，按实体拆批执行的主线是：

1. 可选先执行一次全局 `update`
2. 通过 `build_work_items(...)` 构建实体工作项队列
3. 单实体依次准备所需 WAD
4. 执行 `extract`
5. 执行 `mapping`
6. 清理当前实体远端产物

目标是降低磁盘峰值，而不是把 `extract + mapping` 合并成一个大步骤。

## 5. 上下文约束

- `DataReader` 构造必须传入 `ctx: AppContext`
- `AudioEntityData.from_champion/from_map` 必须传入 `ctx`
- 解包、映射、remote 准备相关主函数都要求显式上下文
