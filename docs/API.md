# lol_audio_unpack API 文档

本文档集合描述 `lol_audio_unpack` 当前可用的 Python API 与命令行 API，基于源码目录 `src/lol_audio_unpack/`（当前分支版本）。

## 文档导航

- [API 导航与约定](./api/README.md)
- [Python API（公开入口与管理器）](./api/python_api.md)
- [CLI API（命令行参数与执行语义）](./api/cli_api.md)
- [解包与映射 API（核心流水线）](./api/pipeline_api.md)
- [配置与数据读写 API](./api/config_api.md)

## 稳定性分级

- `稳定公开`：`setup_app`、`AppContext`、`OperationOptions`、`LolAudioUnpackApp`、`unpack` CLI。
- `半稳定`：`create_app_context`、`initialize_context_from_env`、`DataUpdater/BinUpdater/DataReader` 构造与公开方法（推荐通过 Facade 间接调用）。
- `内部实现`：以下划线开头的方法/函数（如 `_extract_bin_raws`、`_get_cached_hirc`），默认不保证兼容。

> 说明：主链路已彻底移除“未传 `ctx` 时回退全局 `config`”机制；所有核心调用均要求显式上下文。

## 快速示例

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, setup_app

ctx = setup_app(dev_mode=False, log_level="INFO")
app = LolAudioUnpackApp(ctx)

app.update(OperationOptions(force_update=False), target="all")
app.extract(OperationOptions(max_workers=4, champion_ids=(1, 103)), include_maps=False)
```

```bash
uv run unpack --update --extract --max-workers 8
```
