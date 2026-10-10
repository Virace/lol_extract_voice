# API 总览

在 Python 脚本中调用本地音频处理能力。推荐从应用编排入口开始，只有复用单一能力时再直接使用对应模块。

## 按用途选择入口

| 我想做什么 | 推荐入口 | 说明 |
| --- | --- | --- |
| 初始化应用与目录 | [`setup_app`](api/python_api.md#setup-app)、[`create_app_context`](api/python_api.md#create-app-context) | [本地数据源要求](api/prepared_source.md) |
| 更新、解包、映射、转码 | [`LolAudioUnpackApp`](api/python_api.md#lolaudiounpackapp) | [调用示例](api/python_api.md#examples) |
| 设置单次处理范围 | [`OperationOptions`](api/python_api.md#operationoptions) | [运行上下文](api/config_api.md#app-context) |
| 检查执行结果 | [`StageResult`](api/python_api.md#stageresult)、[`RunResult`](api/python_api.md#runresult) | [结果类型](api/python_api.md#types) |
| 使用命令行自动化 | [控制台参数](api/cli_api.md) | [控制台上手](cli-package.md) |

## 模块与公开符号

### [根包入口](api/python_api.md#root)

导入路径：`lol_audio_unpack` · [查看包入口](../src/lol_audio_unpack/__init__.py)

- [`setup_app`](api/python_api.md#setup-app)
- [`__version__`](api/python_api.md#version)

### [应用编排](api/python_api.md#package-app)

导入路径：`lol_audio_unpack.app` · [查看包入口](../src/lol_audio_unpack/app/__init__.py)

- [`create_app_context`](api/python_api.md#create-app-context)
- [`AppConfig`](api/python_api.md#appconfig)
- [`AppPaths`](api/python_api.md#apppaths)
- [`AppContext`](api/python_api.md#appcontext)
- [`AppContextValidationError`](api/python_api.md#appcontextvalidationerror)
- [`OperationOptions`](api/python_api.md#operationoptions)
- [`WavOutputOptions`](api/python_api.md#wavoutputoptions)
- [`LolAudioUnpackApp`](api/python_api.md#lolaudiounpackapp)
- [`ResourcePackWadRef`](api/python_api.md#resourcepackwadref)
- [`OperationProgress`](api/python_api.md#operationprogress)
- [`ResultStatus`](api/python_api.md#resultstatus)
- [`EntityResult`](api/python_api.md#entityresult)
- [`StageResult`](api/python_api.md#stageresult)
- [`RunResult`](api/python_api.md#runresult)

### [配置与 INI](api/python_api.md#config)

导入路径：`lol_audio_unpack.config` · [查看包入口](../src/lol_audio_unpack/config/__init__.py)

- [`SettingKey`](api/python_api.md#settingkey)
- [`ConfigSection`](api/python_api.md#configsection)
- [`SharedSettingField`](api/python_api.md#sharedsettingfield)
- [`CommandConfigField`](api/python_api.md#commandconfigfield)
- [`build_settings`](api/python_api.md#build-settings)
- [`load_settings`](api/python_api.md#load-settings)
- [`write_settings`](api/python_api.md#write-settings)
- [`load_command_config`](api/python_api.md#load-command-config)
- [`write_command_config`](api/python_api.md#write-command-config)
- [`resolve_default_path`](api/python_api.md#resolve-default-path)

### [音频解包](api/python_api.md#unpack)

导入路径：`lol_audio_unpack.unpack` · [查看包入口](../src/lol_audio_unpack/unpack/__init__.py)

- [`generate_output_path`](api/python_api.md#generate-output-path)
- [`unpack_all`](api/python_api.md#unpack-all)
- [`unpack_entity`](api/python_api.md#unpack-entity)
- [`unpack_champion`](api/python_api.md#unpack-champion)
- [`unpack_champions`](api/python_api.md#unpack-champions)
- [`unpack_map`](api/python_api.md#unpack-map)
- [`unpack_maps`](api/python_api.md#unpack-maps)
- [`unpack_resource_pack`](api/python_api.md#unpack-resource-pack)
- [`unpack_resource_packs`](api/python_api.md#unpack-resource-packs)

### [事件映射](api/python_api.md#mapping)

导入路径：`lol_audio_unpack.mapping` · [查看包入口](../src/lol_audio_unpack/mapping/__init__.py)

- [`RuntimeCache`](api/python_api.md#runtimecache)
- [`build_all`](api/python_api.md#build-all)
- [`build_entity`](api/python_api.md#build-entity)
- [`build_champion`](api/python_api.md#build-champion)
- [`build_champions`](api/python_api.md#build-champions)
- [`build_map`](api/python_api.md#build-map)
- [`build_maps`](api/python_api.md#build-maps)
- [`build_resource_pack`](api/python_api.md#build-resource-pack)
- [`build_resource_packs`](api/python_api.md#build-resource-packs)
- [`execute_tasks`](api/python_api.md#execute-tasks)
- [`integrate_entity`](api/python_api.md#integrate-entity)
- [`describe_hirc_backend`](api/python_api.md#describe-hirc-backend)

### [数据模型](api/python_api.md#model)

导入路径：`lol_audio_unpack.model` · [查看包入口](../src/lol_audio_unpack/model/__init__.py)

- [`AudioEntityData`](api/python_api.md#audioentitydata)
- [`generate_champion_tasks`](api/python_api.md#generate-champion-tasks)
- [`generate_map_tasks`](api/python_api.md#generate-map-tasks)

### [WAV 转码](api/python_api.md#wav)

导入路径：`lol_audio_unpack.runtime.wav` · [查看包入口](../src/lol_audio_unpack/runtime/wav/__init__.py)

- [`TranscodeCoordinator`](api/python_api.md#transcodecoordinator)
- [`TranscodePaths`](api/python_api.md#transcodepaths)
- [`TranscodeProgress`](api/python_api.md#transcodeprogress)
- [`TranscodeSummary`](api/python_api.md#transcodesummary)
- [`build_output_path`](api/python_api.md#build-output-path)
- [`build_transcode_paths`](api/python_api.md#build-transcode-paths)
- [`resolve_decode_config`](api/python_api.md#resolve-decode-config)
- [`run_tree`](api/python_api.md#run-tree)
- [`run_worker`](api/python_api.md#run-worker)

### [数据准备与读取](api/python_api.md#manager)

导入路径：`lol_audio_unpack.manager` · [查看包入口](../src/lol_audio_unpack/manager/__init__.py)

- [`DataUpdater`](api/python_api.md#dataupdater)
- [`BinUpdater`](api/python_api.md#binupdater)
- [`DataReader`](api/python_api.md#datareader)
- [`ResourcePackDiscovery`](api/python_api.md#resourcepackdiscovery)

## 继续阅读

- [Python API](api/python_api.md)
- [配置文件与设置](api/config_api.md#config-files)
- [运行上下文](api/config_api.md#app-context)
- [解包与映射流水线](api/pipeline_api.md)
- [模块与数据结构](api/README.md)
- [本地数据源要求](api/prepared_source.md)
