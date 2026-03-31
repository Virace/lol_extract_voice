# API 导航与约定

## 1. 模块视图

- 入口层：`lol_audio_unpack/__init__.py`、`lol_audio_unpack/__main__.py`
- 上下文与配置层：`app_context.py`
- 数据准备层：`manager/data_updater.py`、`manager/bin_updater.py`
- 数据读取层：`manager/data_reader.py`
- 解包层：`unpack.py`
- 映射层：`mapping.py`
- 数据模型层：`model.py`
- 通用能力：`manager/utils.py`、`utils/path_constants.py`

## 2. 典型调用链

### 2.1 CLI 主链

1. 参数解析与校验（`create_parser` / `validate_args`）
2. 初始化应用（`setup_app` -> `create_app_context`）
3. `local_path` 下按顺序执行：更新 -> 解包 -> 映射
4. `remote_snapshot` 下：
   - `update` 仍全局执行一次
   - 若存在 `extract` / `mapping`，则改走“单位驱动”：
     - 按英雄 / 地图逐个执行
     - 单位完成后立即清理当前远端 WAD
4. 结果写入 `OUTPUT_PATH` 衍生目录（`manifest`、`audios`、`hashes`、`reports`）

### 2.2 Python 主链

1. `ctx = setup_app(...)`
2. `app = LolAudioUnpackApp(ctx)`
3. 通过 `OperationOptions` 传参
4. 调用 `app.update(...)` / `app.extract(...)` / `app.mapping(...)`

> 说明：全局 `config` 兼容路径已移除，主链路必须显式持有 `AppContext`。
>
> 说明：remote 模式的真实 live 长测统一打上 `remote_live` marker，默认不在常规 `pytest` 中执行。
>
> 说明：英雄筛选当前支持稳定 `ID` 与稳定 `alias` 两种方式，二者都会解析到同一个英雄 ID；`name` 不在推荐支持范围内。

## 3. 延伸文档

- [Remote 模式（运行与接入）](./remote_mode.md)
- [基准测试与性能参考](./benchmarking_and_performance.md)

## 4. 目录输出约定

- `manifest/<version>/data.*`：基础聚合数据（英雄/地图元信息）
- `manifest/<version>/banks/**`：分类后的 bank 路径数据
- `manifest/<version>/events/**`：事件数据
- `manifest/<version>/bin_input/**`：remote 模式为 `BinUpdater` 准备的稀疏 BIN 输入
- `audios/<version>/...`：解包出的 `.wem`
- `hashes/<version>/...`：映射结果或整合结果
- `reports/<version>/...`：单实体解包汇总报告
- `cache/remote/**`：remote 模式下载缓存
- `_prepared_game/**`：remote 模式最小运行环境

## 5. 数据格式约定

`write_data(data, base_path, dev_mode=...)` 会根据模式决定写入格式：

- 开发模式：优先写 `.yml`
- 非开发模式：优先写 `.msgpack`

`read_data(path, dev_mode=...)` 会按优先级自动寻找可读文件。
