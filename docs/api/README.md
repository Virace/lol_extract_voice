# API 导航与约定

## 1. 模块视图

- 入口层：`lol_audio_unpack/__init__.py`、`lol_audio_unpack/__main__.py`
- 数据准备层：`manager/data_updater.py`、`manager/bin_updater.py`
- 数据读取层：`manager/data_reader.py`
- 解包层：`unpack.py`
- 映射层：`mapping.py`
- 数据模型层：`model.py`
- 配置与通用能力：`utils/config.py`、`manager/utils.py`、`utils/path_constants.py`

## 2. 典型调用链

### 2.1 CLI 主链

1. 参数解析与校验（`create_parser` / `validate_args`）
2. 初始化应用（`setup_app` + `config.initialize`）
3. 按顺序执行：更新 -> 解包 -> 映射
4. 结果写入 `OUTPUT_PATH` 衍生目录（`manifest`、`audios`、`hashes`、`reports`）

### 2.2 Python 主链

1. `setup_app(...)`
2. `DataUpdater.check_and_update()`
3. `reader = DataReader()`
4. 调用 `unpack_*` 或 `build_*_mapping`

## 3. 目录输出约定

- `manifest/<version>/data.*`：基础聚合数据（英雄/地图元信息）
- `manifest/<version>/banks/**`：分类后的 bank 路径数据
- `manifest/<version>/events/**`：事件数据
- `audios/<version>/...`：解包出的 `.wem`
- `hashes/<version>/...`：映射结果或整合结果
- `reports/<version>/...`：单实体解包汇总报告

## 4. 数据格式约定

`write_data(data, base_path)` 会根据模式决定写入格式：

- 开发模式：优先写 `.yml`
- 非开发模式：优先写 `.msgpack`

`read_data(path)` 则会按优先级自动寻找可读文件。
