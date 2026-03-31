# 解包与映射 API（核心流水线）

## 1. 解包 API（`unpack.py`）

### 1.1 核心函数签名

```python
def unpack_audio_entity(
    entity_data: AudioEntityData,
    reader: DataReader,
    wad_cache: dict[Path, WAD] | None = None,
    cache_lock: threading.Lock | None = None,
    *,
    ctx: AppContext,
) -> None
```

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

```python
def unpack_audio_all(..., *, ctx: AppContext) -> None
def unpack_champions(..., *, ctx: AppContext) -> None
def unpack_maps(..., *, ctx: AppContext) -> None
```

### 1.2 输出路径规则

`generate_output_path` 受 `ctx.config.group_by_type` 影响：

- `True`：`audios/<type>/<entity_path>`
- `False`：`audios/<entity_path>/<type>`

其中 `<entity_path>` 使用 `utils/path_constants.py` 的命名约定（`ID·alias·name...`）。

### 1.3 解包过程（单实体）

1. 收集 VO 与非 VO bank 路径。
2. 分别从语言 WAD / 根 WAD 批量提取原始数据。
3. 解析 `BNK` / `WPK` 并输出 `.wem`。
4. 记录统计信息并写出 `_metadata.yaml` 报告。
5. 英雄解包在 `WITH_BP_VO` 启用时附带写入大厅选用/禁用语音。

### 1.4 remote 模式下的解包准备

在 `remote_snapshot` 模式下，`facade.extract()` 会先准备当前操作所需的实体 WAD：

- 仅 `VO`：只准备语言 WAD
- 含 `SFX/MUSIC`：准备 root WAD
- 若同一实体同时命中两类内容：两者都准备

## 2. 映射 API（`mapping.py`）

### 2.1 核心函数签名

```python
def build_audio_event_mapping(
    entity_data: AudioEntityData,
    reader: DataReader,
    wwiser_manager: WwiserManager | None = None,
    integrate_data: bool = False,
    runtime_cache: MappingRuntimeCache | None = None,
    *,
    ctx: AppContext,
) -> dict[str, Any]
```

```python
def build_mapping_all(..., *, ctx: AppContext) -> None
def build_champions_mapping(..., *, ctx: AppContext) -> None
def build_maps_mapping(..., *, ctx: AppContext) -> None
```

### 2.2 映射结果写入

- 普通映射：写入 `hashes/<version>/<champions|maps>/<id>.*`
- 整合数据（`integrate_data=True`）：写入 `hashes/<version>/integrated/<champions|maps>/<id>.*`

### 2.3 缓存机制

`MappingRuntimeCache` 包含：

- `wad_cache`：复用 WAD 对象
- `extract_cache`：避免重复提取同一 bnk
- `hirc_cache`：复用 HIRC 解析对象
- `cache_lock`：并发访问保护

### 2.4 当前 `mapping` 的真实处理边界

`mapping` 当前不是只处理 `VO`。

真实语义是：

1. 只要某个 `category` 同时出现在 `banks` 与 `events` 中，就会尝试构建映射
2. 再根据 `category` 是否包含 `VO` 决定 WAD 来源：
   - 包含 `VO`：语言 WAD
   - 其他：root WAD

因此：

- `mapping` 通常会同时需要 root + 语言两类 WAD
- 它不受 `include_types` 约束
- 地图 `mapping` 往往会更慢，因为常同时卷入环境音效、音乐和 VO/NPC 事件

## 3. 上下文约束

- `DataReader` 构造必须传入 `ctx: AppContext`。
- `AudioEntityData.from_champion/from_map` 必须传入 `ctx`。
- 解包与映射主函数均要求 `ctx`，不再支持全局配置回退。

## 4. remote 模式执行顺序

在 `remote_snapshot` 模式下，CLI 不再简单地整批执行 `extract` / `mapping`，而是：

1. 全局完成 `update`
2. 构建实体 work item 队列
3. 单位执行：
   - 准备当前实体所需 WAD 并集
   - 运行 `extract`
   - 运行 `mapping`
   - 清理当前实体远端 WAD

这样做的目标是降低峰值空间占用，而不是追求 `extract + mapping` 的逻辑融合。

## 5. 半稳定与内部边界

建议直接调用：

- `unpack_audio_all` / `unpack_champions` / `unpack_maps`
- `build_mapping_all` / `build_champions_mapping` / `build_maps_mapping`

不建议外部直接依赖：

- `_get_wad_instance`
- `_generate_relative_path`
- `_get_cached_hirc`
- `_is_bnk_extracted` / `_mark_bnk_extracted`

这些内部函数可能在后续优化时重构而不做兼容承诺。
