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

## 3. 上下文约束

- `DataReader` 构造必须传入 `ctx: AppContext`。
- `AudioEntityData.from_champion/from_map` 必须传入 `ctx`。
- 解包与映射主函数均要求 `ctx`，不再支持全局配置回退。

## 4. 半稳定与内部边界

建议直接调用：

- `unpack_audio_all` / `unpack_champions` / `unpack_maps`
- `build_mapping_all` / `build_champions_mapping` / `build_maps_mapping`

不建议外部直接依赖：

- `_get_wad_instance`
- `_generate_relative_path`
- `_get_cached_hirc`
- `_is_bnk_extracted` / `_mark_bnk_extracted`

这些内部函数可能在后续优化时重构而不做兼容承诺。
