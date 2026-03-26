# 文档导航

本文档承接 `README.md` 中下沉的详细说明，集中存放 GUI 当前状态、Remote 模式、基准测试与设计说明。

## 1. 使用与接入入口

- [API 总览](./API.md)
- [CLI 参数与执行语义](./api/cli_api.md)
- [配置与数据读写 API](./api/config_api.md)
- [Remote 模式（运行与接入）](./api/remote_mode.md)
- [基准测试与性能参考](./api/benchmarking_and_performance.md)
- [GUI 共享实体数据刷新说明](./gui/shared_entity_data_refresh.md)

## 2. GUI 当前状态

| 功能 | 状态 | 说明 |
| --- | --- | --- |
| 执行解包 | 已完成 | 当前 GUI 可创建并执行音频解包任务。 |
| 生成映射 | 已完成 | 当前 GUI 可创建并执行映射任务。 |
| 查看映射 | 已完成 | 当前 GUI 已具备映射结果查看链路。 |
| 音频试听 | 待完成 | GUI 内试听链路后续补齐。 |
| 转码等功能 | 待完成 | GUI 内转码与后处理能力后续补齐。 |

## 3. Remote 模式

Remote 模式适合：

- 没有本地完整游戏客户端
- 运行环境磁盘受限（CI、容器、临时服务器）
- 只想处理少量英雄 / 地图

Remote 模式不适合：

- 已经有稳定的本地完整客户端
- 需要频繁重复处理大量实体
- 更关注总耗时而不是磁盘峰值

当前关键信息：

- 使用上游 `RiotManifest` 提供的一对已对齐 LCU / GAME manifest
- `update` 全局执行一次，`extract / mapping` 按实体顺序执行
- 单实体完成后会清理当前远端 WAD
- remote 模式主要优化磁盘峰值，不优化总耗时

详细说明见：

- [Remote 模式（运行与接入）](./api/remote_mode.md)

## 4. 基准测试与性能参考

项目内置基准脚本：`scripts/benchmark_cli.py`。

核心口径：

- `--mode mock` 用于轻量自检
- `--mode local_game` 用于本地客户端小样本真实测试
- `mapping` 通常比 `extract` 更重
- 地图 `mapping` 往往比英雄链路更慢

详细参数、示例命令、输出结构与历史性能参考见：

- [基准测试与性能参考](./api/benchmarking_and_performance.md)

## 5. 设计哲学

- **速度优先**：通过简化流程和优化 I/O，尽量提升解包效率。
- **数据纯粹**：不对输出文件做重命名或分类，文件名即游戏数据中的原始 ID。
- **责任分离**：核心能力专注于更新、解包、映射；转码等后处理保持解耦。
