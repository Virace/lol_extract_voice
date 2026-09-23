# CLI 本地打包与验收

用户使用说明见 [控制台独立包](../cli-package.md)。

## 本地构建

开发机需要原生 Windows x64、项目支持的 x64 Python 和 uv，原生依赖必须具有匹配的 wheel。先在仓库根目录执行：

```powershell
uv run --no-sync python scripts/pyinstaller/build_cli.py
```

入口只用标准库，也可直接由已安装 Python 执行。它为每次构建创建 `.temp/cli-package/` 下独立目录，通过锁文件安装核心与 build 依赖，不修改仓库根 `.venv`，不安装 Qt。

默认产物为单文件 `dist/LolAudioUnpack-CLI.exe`；旁边有 `LolAudioUnpack-CLI.exe.sha256` 和 `CLI-README.md`，构建根目录有 `build.log`、`build.json`、依赖环境与 PyInstaller 分析记录。

CLI 使用 `scripts/pyinstaller/assets/cli_icon.ico`，在 GUI 图标的基础上增加终端角标。
同目录的 `cli_icon.png` 保留图标原图；ICO 包含 16、24、32、48、64、128、256 像素尺寸，
仅作为构建时的 EXE 图标资源，不引入 GUI 运行依赖。

支持 `--output-root <新目录>`、`--mode onedir` 和无文件副作用的 `--dry-run`。已存在的输出根目录会被拒绝，不自动覆盖或清理历史产物。目录模式仅用于排障，最终仍需验收单文件。

构建目录默认保留，确认不再需要环境、日志和产物后由用户删除对应任务目录。

## 验收边界

构建成功不等于验收完成。应直接运行该份 EXE，核对版本、退出码、不同调用目录、中文/空格路径、INI、重定向、真实 update/extract/mapping/WAV 和取消行为，并检查构建归档不含 Qt。

在未安装 Python/Qt 的独立 Windows 环境运行后，才能确认免开发环境交付；清空 PATH 不替代此项。真实音频需独立解码核对或人工试听，历史样本与外部后端缺少条件时分别记录为未验证。

本地试用通过后再安排发布；本构建命令不修改 workflow、不上传文件，也不创建 Release。

## Release 附件

`.github/workflows/release-build.yml` 在 main 所包含的提交上收到 tag 推送后构建发布包。
GUI 与 CLI 分别构建，共用版本规则；现有离线与 GUI 行为检查、CLI 工具自检和两份 EXE
的版本一致性检查通过后，才会发布同一个 Release。构建版本取自触发发布的 tag（去掉开头的
`v`），附件准备时同时核对 EXE 版本与 tag。CLI 的构建环境只安装核心和 build 依赖。

附件包括：

- `LolAudioUnpack-<tag>-windows-x64.exe` 及对应 `.sha256`
- `LolAudioUnpack-CLI-<tag>-windows-x64.exe` 及对应 `.sha256`
- `LolAudioUnpack-CLI-README.md`

发布说明优先读取 `.github/release-notes/<tag>.md`，没有对应文件时自动生成。
本地执行构建命令不会触发发布。

构建因 runner 或发布流程问题中断时，可在 Actions 手动运行 `release-build`，填写已有 tag。
手动入口使用当前工作流，但校验并检出该 tag 的精确提交，只接受已包含于 `main` 的提交；
不会移动 tag，也不会把当前 `main` 的产品代码冒充该版本发布。
