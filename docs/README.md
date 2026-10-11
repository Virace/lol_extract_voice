# 文档导航

下载和项目简介见 [README](../README.md)。按使用方式选择入口：

版本变化见 [更新日志](changelog.md)。

| 使用方式 | 从这里开始 | 继续阅读 |
| --- | --- | --- |
| 用界面选择、试听和导出 | [界面使用说明](gui/usage.md) | [常见问题](faq.md#界面使用) |
| 用控制台批量处理 | [控制台使用说明](cli-package.md) | [完整参数](api/cli_api.md) |
| Python 脚本集成 | [API 总览](API.md) | [公开入口](api/python_api.md) |

## 界面使用

- [使用说明](gui/usage.md)：设置目录、创建任务、查找试听与选择导出

## 控制台使用

- [使用说明](cli-package.md)
- [音频筛选](cli-package.md#audio-types)
- [完整参数](api/cli_api.md)
- [配置文件模式](api/cli_api.md#config-file) · [示例配置](../config/lol-audio-unpack.example.ini)

## 其他信息

- [音频文件与输出目录](audio-and-output.md)：音频分组、文件位置、共享与备份
- [本地游戏目录](api/prepared_source.md)：已安装客户端或单独准备的资源目录
- [常见问题](faq.md)：按界面、控制台和共用问题分组

## API

- [API 总览](API.md)：公开入口与模块索引
- [Python API](api/python_api.md)：在脚本中调用更新、解包、映射与 WAV 转码
- [配置文件与设置](api/config_api.md#config-files)
- [运行上下文](api/config_api.md#app-context)
- [解包与映射 API](api/pipeline_api.md)
- [内部数据格式与转换](api/README.md#data-format)
- [资源库 API](api/library_api.md)：索引、共享、输出布局与迁移

## 开发与构建

- [开发文档](development/README.md)：环境、代码结构和检查命令
- [音频 ID 与内容实测](research/historical-wem.md)：跨版本换号与 WEM 内容共享
- [事件名与事件范围实测](research/historical-events.md)：事件改名、候选音频变化与分析资料包
- [控制台本地打包与验收](development/cli-packaging.md)
- [基准测试与性能参考](api/benchmarking_and_performance.md)
- [界面共享实体数据刷新](gui/shared_entity_data_refresh.md)
- [界面任务与导出规则](development/gui-tasks-and-exports.md)
- [本地数据源验证合同](development/prepared-source-contract.md)
- [产品定位](../PRODUCT.md)、[项目约束](../PROJECT_CONSTRAINTS.md)、[架构与页面设计](../PROJECT_DESIGN.md)
