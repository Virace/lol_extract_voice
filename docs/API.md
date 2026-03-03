# lol_audio_unpack API 文档

本文档集合描述 `lol_audio_unpack` 当前可用的 Python API 与命令行 API，基于源码目录 `src/lol_audio_unpack/`（当前分支版本）。

## 文档导航

- [API 导航与约定](./api/README.md)
- [Python API（公开入口与管理器）](./api/python_api.md)
- [CLI API（命令行参数与执行语义）](./api/cli_api.md)
- [解包与映射 API（核心流水线）](./api/pipeline_api.md)
- [配置与数据读写 API](./api/config_api.md)

## 稳定性分级

- `稳定公开`：`lol_audio_unpack` 包根导出符号、`unpack` CLI、`DataUpdater/BinUpdater/DataReader` 的公开方法。
- `半稳定`：`model.py`、`unpack.py`、`mapping.py` 的模块级函数（适合二次开发调用，但未来可能调整）。
- `内部实现`：以下划线开头的方法/函数（如 `_extract_bin_raws`、`_get_cached_hirc`），默认不保证兼容。

## 快速示例

```python
from lol_audio_unpack import DataUpdater, DataReader, setup_app
from lol_audio_unpack.unpack import unpack_champions

setup_app(dev_mode=False, log_level="INFO")
DataUpdater(force_update=False).check_and_update()
reader = DataReader()
unpack_champions(reader=reader, champion_ids=[1, 103], max_workers=4)
```

```bash
uv run unpack --update --extract --max-workers 8
```
