# lol_audio_unpack API 文档

本文档集合描述 `lol_audio_unpack` 当前可用的 Python API 与命令行 API，基于源码目录 `src/lol_audio_unpack/`（当前分支版本）。

## 文档导航

- [API 导航与约定](./api/README.md)
- [Python API（公开入口与管理器）](./api/python_api.md)
- [CLI API（命令行参数与执行语义）](./api/cli_api.md)
- [Remote 模式（运行与接入）](./api/remote_mode.md)
- [解包与映射 API（核心流水线）](./api/pipeline_api.md)
- [配置与数据读写 API](./api/config_api.md)

## 稳定性分级

- `稳定公开`：`setup_app`、`AppContext`、`OperationOptions`、`LolAudioUnpackApp`、`unpack` CLI。
- `半稳定`：`create_app_context`、`DataUpdater/BinUpdater/DataReader` 构造与公开方法（推荐通过 Facade 间接调用）。
- `内部实现`：`remote_preparer.py`、以下划线开头的方法/函数（如 `_extract_bin_raws`、`_get_cached_hirc`），默认不保证兼容。

> 说明：主链路已彻底移除“未传 `ctx` 时回退全局 `config`”机制；所有核心调用均要求显式上下文。
>
> 说明：remote 模式当前已具备英雄 `update / extract / mapping` 的真实远端验证；地图链路中的 `mapping` 仍属于长耗时专项验收项。
>
> 说明：英雄筛选当前支持稳定 `ID` 与稳定 `alias` 两种方式，二者都会解析到同一个英雄 ID；`name` 不在推荐支持范围内。

## 快速示例

```python
from lol_audio_unpack import LolAudioUnpackApp, OperationOptions, setup_app

ctx = setup_app(
    dev_mode=False,
    log_level="INFO",
    settings={
        "GAME_PATH": "/path/to/League of Legends",
        "OUTPUT_PATH": "./output",
        "GAME_REGION": "zh_CN",
    },
)
app = LolAudioUnpackApp(ctx)

app.update(OperationOptions(force_update=False), target="all")
app.extract(OperationOptions(max_workers=4, champion_ids=(1, 103)), include_maps=False)
```

```bash
uv run unpack update --game-path "/path/to/League of Legends" --output-path "./output"
```

```bash
# remote_snapshot 默认自动解析最新 live 快照
uv run unpack extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```
