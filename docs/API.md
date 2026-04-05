# lol_audio_unpack API 文档

本文档集合只描述 `src/lol_audio_unpack/` 当前分支仍建议使用的最新公开入口。

## 1. 推荐导入面

- `lol_audio_unpack`
  - `setup_app`
  - `__version__`
- `lol_audio_unpack.app`
  - `create_app_context`
  - `AppConfig`
  - `AppPaths`
  - `AppContext`
  - `AppContextValidationError`
  - `OperationOptions`
  - `WavOutputOptions`
  - `RemoteSnapshotConfig`
  - `SourceMode`
  - `LolAudioUnpackApp`
  - `RemoteEntityWorkItem`
  - `RemoteEntityCallbackPayload`
- `lol_audio_unpack.config`
  - `SettingKey`
  - `ConfigSection`
  - `SharedSettingField`
  - `CommandConfigField`
  - `build_settings`
  - `load_settings`
  - `write_settings`
  - `load_command_config`
  - `write_command_config`
  - `resolve_default_path`
- `lol_audio_unpack.unpack`
  - `generate_output_path`
  - `unpack_all`
  - `unpack_entity`
  - `unpack_champion`
  - `unpack_champions`
  - `unpack_map`
  - `unpack_maps`
- `lol_audio_unpack.mapping`
  - `RuntimeCache`
  - `build_all`
  - `build_entity`
  - `build_champion`
  - `build_champions`
  - `build_map`
  - `build_maps`
  - `execute_tasks`
  - `integrate_entity`
  - `describe_hirc_backend`
- `lol_audio_unpack.model`
  - `AudioEntityData`
  - `generate_champion_tasks`
  - `generate_map_tasks`
- `lol_audio_unpack.runtime.remote`
  - `RemotePreparer`
  - `LcuResult`
  - `BinInputResult`
  - `GameWadResult`
- `lol_audio_unpack.runtime.wav`
  - `JobSpec`
  - `JobHandle`
  - `ManifestRecorder`
  - `TranscodeCoordinator`
  - `TranscodeProgress`
  - `TranscodeSummary`
  - `build_job_spec`
  - `build_recorder`
  - `launch_detached`
  - `launch_job`
  - `parse_job_spec`
  - `run_job`
  - `build_output_path`
  - `resolve_decode_config`
  - `run_worker`
- `lol_audio_unpack.manager`
  - `DataUpdater`
  - `BinUpdater`
  - `DataReader`

## 2. 导入建议

- 需要完整编排能力时，优先使用 `setup_app` + `lol_audio_unpack.app`。
- 需要显式构建上下文、编写 GUI/脚本接入时，优先使用 `lol_audio_unpack.app` 与 `lol_audio_unpack.config`。
- 只复用单一解包或映射能力时，直接导入 `lol_audio_unpack.unpack` 或 `lol_audio_unpack.mapping`。
- 只有在需要 remote 资源准备或 WAV sidecar 转码时，再下沉到 `lol_audio_unpack.runtime.remote` 与 `lol_audio_unpack.runtime.wav`。
- `lol_audio_unpack.manager` 更接近底层数据准备/读取层，适合脚本化或测试场景。

## 3. 快速示例

```python
from lol_audio_unpack import setup_app
from lol_audio_unpack.app import LolAudioUnpackApp, OperationOptions

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
uv run unpack extract \
  --output-path "/tmp/lol-remote" \
  --game-region zh_CN \
  --source-mode remote_snapshot \
  --champions 1,103,555
```

## 4. 文档导航

- [API 导航与模块视图](./api/README.md)
- [Python API（分域包与公开入口）](./api/python_api.md)
- [CLI API（命令行参数与执行语义）](./api/cli_api.md)
- [Remote 模式（运行与接入）](./api/remote_mode.md)
- [解包与映射 API（核心流水线）](./api/pipeline_api.md)
- [配置与上下文 API](./api/config_api.md)
