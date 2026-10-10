# 文档网站维护

文档网站使用 VitePress，Node 项目的依赖、锁文件和配置全部位于 `docs/`。
Python 程序仍在仓库根目录通过 uv 安装和运行；普通使用和 Python 开发无需安装文档依赖。

## 本地运行

安装 Node.js 22.12 或更新版本，然后在 `docs/` 中执行：

```powershell
cd docs
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173/>。修改根 README 或文档正文后，开发服务器会更新页面。
命令绑定本机地址，端口被占用时会明确失败，不会自动切换到其他端口。

检查正式构建效果：

```powershell
npm run build
npm run preview
```

打开 <http://127.0.0.1:4173/>。预览服务使用刚才构建的静态文件；修改正文后需要重新构建，
再重启预览服务，以免保留旧的页面和资源路径。
此命令使用 Vite 的静态预览入口，明确绑定本机地址；VitePress 当前预发布版本的预览入口会忽略 `--host`。
在终端按 `Ctrl+C` 停止服务。

## 正文与页面

- 根 [README](../../README.md) 直接生成项目介绍页；首页简介与能力列表也读取它。
- `docs/index.md` 仅声明首页布局，按钮和版本由构建配置与公开 Release 信息组合。
- `docs/` 下现有 Markdown 直接生成详细页面，文件继续保持 GitHub 可阅读的格式。
- 网站导航、侧边栏、主题和本地搜索由 `.vitepress/config.mts` 管理。
- `.vitepress/source.mts` 只处理发布范围、链接和原始资源，不改写 Markdown 正文。

导航按界面使用、控制台使用、其他信息、API、开发与构建划分。命令示例与参数放在控制台区；
音频分组、输出目录和本地输入放在“其他信息”；配置读写接口与运行上下文放在 API 区。

首页为 `/`，根 README 映射到 `/project.html`，详细页保留 `/docs/` 路径。文档之间继续写相对 `.md` 链接，
网站构建时适配链接；返回根 README 的中文锚点也保留。

| 内容 | 处理方式 |
| --- | --- |
| 示例 INI、规范、许可证 | 链接到构建提交的 GitHub 文件页，由 GitHub 提供查看和下载 |
| 图片、图标、前端资源 | 打包显示所需资源 |
| 无 Git 元数据的源码归档 | 提示后将源码链接指向主分支 |
| 搜索 | 浏览器本地搜索，无需服务账号 |

## 首页与发布信息

README 中的 `project-summary` 标记包围首页共用简介，“你可以做什么”列表同时生成首页能力介绍。
修改这些内容后开发服务器会重新载入配置。首页不另写说明正文。

| 发布信息 | 规则 |
| --- | --- |
| 获取时机 | 启动开发服务或构建时调用公开 `releases/latest` API，获取版本、更新时间与发布页 |
| 下载按钮 | 显示版本，统一跳转 Release 页面；源码和示例配置仍使用 GitHub 文件页 |
| 缓存 | 本地缓存一小时，位于 `.temp/.docs-site/release.json`；CI 每次重新获取，页面访问不请求 GitHub API |
| 网络失败 | 本地提示并沿用缓存或发布页入口；CI 构建失败，保留线上站点 |
| CI 授权 | 使用 GitHub 自动提供的 `GITHUB_TOKEN` 请求 API，令牌不进入网页 |
| 刷新版本 | 重新构建站点；页面是构建时的发布快照，Release 页面可查看当前版本 |

## 配图维护

`docs/images/` 保存 README 与使用说明共用的界面图。

1. 优先离屏渲染当前界面，创建控件前用 `QFontDatabase.addApplicationFont` 注册微软雅黑、Segoe UI 等实际字体，并设置一致的主题。
2. 使用独立配置，不启动自动更新或音频处理；展示音频时读取已有真实资源。
3. 检查中文、图标和完整布局后采用。录屏帧可补充动态场景，但需核对按钮和操作仍与当前程序一致。

## 依赖与生成文件

`package.json` 和 `package-lock.json` 作为文档源码维护；`node_modules/` 不入库。
VitePress 使用与参考站一致的 `2.0.0-alpha.19`，锁文件固定实际依赖。
主题保留页面淡入、目录指示条平滑移动和桌面目录布局修正；减少动态效果的系统偏好会关闭动画。
更新依赖时同时核对审计、构建和本地预览。

构建产物和缓存统一放在仓库 `.temp/.docs-site/`：

- `dist/`：可部署到任意静态服务器的网站。
- `cache/` 和 `vite-cache/`：框架缓存。
- `npm-cache/`：`docs/.npmrc` 指定的 npm 下载缓存与日志。

这些目录不入库，也不作为正文修改入口。需要调整文案或配置示例时修改原文件，然后重新构建。
本地生成物默认保留，由维护者在停止服务后手动清理。

## Cloudflare Pages 发布

网站使用 Cloudflare Pages，项目名 `lau`，目标域名 `lau.oogoo.top`。仅上传静态文件，不使用 Functions。
网站以 `/` 为基础路径，同一份构建包也可解压到其他静态服务器的站点根目录。

发布入口为 `.github/workflows/docs-deploy.yml`，始终获取 `main` 的文档，首页下载按钮读取最新正式版 Release。

| 更新方式 | 触发与行为 |
| --- | --- |
| 软件正式版发布 | `release-build` 发布成功后直接调用文档 workflow，构建并上传网站 |
| 手动发布或编辑 Release | `published`、`edited` 事件更新网站；草稿和预发布版本跳过 |
| 文档修正 | 修改合入 `main` 后，在 Actions 中手动运行 `docs-deploy` |
| 只生成构建包 | 手动运行时关闭 `deploy`，构建并保存文件，不上传 |

普通代码提交不会触发网站发布。网站上传失败不撤销已发布的软件 Release，可以单独重跑文档 workflow。
并发更新按顺序执行；CI 获取发布信息失败时终止构建，避免用旧缓存覆盖线上版本。

### 首次配置

文档源码和两条 workflow 必须进入 `main`；下一次发版的标签也应包含这些文件。
手动入口只有在 workflow 已进入默认分支后才会出现。

在仓库的 **Settings → Secrets and variables → Actions** 配置：

| Secret | 内容 |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Pages 所属 Cloudflare 账号 ID |
| `CLOUDFLARE_API_TOKEN` | 仅授权对应账号的 **Account → Cloudflare Pages → Edit** 令牌 |

在 Cloudflare 的 [API Tokens](https://dash.cloudflare.com/profile/api-tokens) 页面创建自定义令牌，
权限选 **Account → Cloudflare Pages → Edit**，账号范围选目标账号即可，无需授予 DNS 或令牌管理权限。
令牌通过 Secrets 页面填写，或使用 GH 的隐藏输入：

```sh
gh secret set CLOUDFLARE_API_TOKEN --repo Virace/lol_extract_voice
```

首次上传时 workflow 会创建 `lau` Pages 项目，生产分支设为 `main`；已有项目则检查后使用，不覆盖其配置。
随后在 Cloudflare 的 **Workers & Pages → lau → Custom domains** 绑定 `lau.oogoo.top`，按页面提示确认 DNS 记录。
自定义域名需要同时完成 Pages 绑定和 DNS 配置，仅添加 CNAME 不足以启用站点。
日常更新只需要 Pages 权限，无需再次配置域名。

### 手动更新

在 GitHub 的 **Actions → docs-deploy → Run workflow** 选择 `main`，保持 `deploy` 开启；也可执行：

```sh
gh workflow run docs-deploy.yml --repo Virace/lol_extract_voice --ref main -f deploy=true
```

只生成构建包时，把 `deploy` 关闭或设为 `false`。不需要重跑软件打包流程。

### 构建包与回退

每次成功构建都会先保存 `docs-site-<运行编号>-<重跑次数>` artifact，再上传网站：

| 文件 | 用途 |
| --- | --- |
| `lol-audio-unpack-docs-<提交>.zip` | 解压后直接得到网站根目录文件 |
| `.zip.sha256` | 压缩包 SHA-256 校验值 |
| `.json` | 源码提交、构建时间和 Release 快照 |

构建包保留 90 天，可从 Actions 运行记录下载；长期留存需另外下载保存。
缺少部署凭证或上传失败时，已保存的构建包仍可用于手动发布。
需要回退网站时，在 Pages 的部署记录中回退至之前的生产部署。
