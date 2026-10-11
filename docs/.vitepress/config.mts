import path from 'node:path'
import { createRequire } from 'node:module'
import { defineConfig } from 'vitepress'
import { brandIcon, repoRoot, siteRoot, sourceExcludes, sourceLinks } from './source.mts'
import { readProject } from './home.mts'
import { loadRelease } from './release.mts'
import { renderChangelog } from './changelog.mts'

const require = createRequire(import.meta.url)
const release = await loadRelease()
const changelog = await renderChangelog(release)
const project = readProject()

export default defineConfig({
  lang: 'zh-CN',
  title: 'Lol Audio Unpack',
  description: '英雄联盟音频工具的使用说明与 API 文档。',
  // 构建项目在 docs/，源码目录保留仓库路径，README 无需复制或搬迁。
  srcDir: '..',
  srcExclude: sourceExcludes,
  rewrites: { 'README.md': 'project.md', 'docs/index.md': 'index.md' },
  outDir: path.join(siteRoot, 'dist'),
  cacheDir: path.join(siteRoot, 'cache'),
  useWebFonts: false,
  head: [['link', { rel: 'icon', href: brandIcon, type: 'image/svg+xml' }]],
  markdown: {
    config(md) {
      sourceLinks(md)
      md.core.ruler.before('normalize', 'release-notes', (state) => {
        if (state.env.relativePath === 'docs/changelog.md') {
          state.src = state.src.replace('<!-- release-notes -->', changelog)
        }
      })
    },
  },
  transformPageData(page) {
    if (page.frontmatter.layout !== 'home') return
    page.frontmatter.hero = {
      name: project.name,
      text: '英雄联盟音频工具',
      tagline: project.summary,
      image: { src: brandIcon, alt: project.name },
      actions: [
        { theme: 'brand', text: release.tag ? `下载 ${release.tag}` : '下载', link: release.url },
        { theme: 'alt', text: '开始使用', link: '/docs/gui/usage' },
      ],
    }
    page.frontmatter.features = project.features
    page.frontmatter.release = release
  },
  vite: {
    publicDir: false,
    cacheDir: path.join(siteRoot, 'vite-cache'),
    server: {
      fs: { allow: [repoRoot] },
      watch: { ignored: ['**/.temp/**', '**/.venv/**'] },
    },
    plugins: [{
      name: 'docs:readme-home',
      handleHotUpdate({ file, server }) {
        if (file === path.join(repoRoot, 'README.md')) server.restart()
      },
    }, {
      name: 'docs:dependency-resolution',
      enforce: 'post',
      config(config) {
        // Vite 的嵌套预构建请求以源码根目录解析，改由 docs/ 包定位依赖入口。
        const include = config.optimizeDeps?.include
        if (include) {
          config.optimizeDeps!.include = include.map((id) => id.startsWith('vitepress > ')
            ? require.resolve(id.slice('vitepress > '.length))
            : id)
        }
      },
    }],
    // 根 README 位于 Node 子项目之外，Vue 始终从 docs/ 的依赖解析。
    resolve: {
      alias: [
        { find: 'vue/server-renderer', replacement: require.resolve('@vue/server-renderer/dist/server-renderer.esm-bundler.js') },
        { find: 'vue', replacement: require.resolve('vue/dist/vue.runtime.esm-bundler.js') },
      ],
    },
  },
  themeConfig: {
    logo: { src: brandIcon, alt: 'Lol Audio Unpack' },
    nav: [
      { text: '首页', link: '/' },
      { text: '更新日志', link: '/docs/changelog' },
      {
        text: '使用说明',
        items: [
          { text: '文档导航', link: '/docs/README' },
          { text: '界面使用', link: '/docs/gui/usage' },
          { text: '控制台使用', link: '/docs/cli-package' },
          { text: '其他信息', link: '/docs/audio-and-output' },
        ],
      },
      { text: 'API', link: '/docs/API' },
      { text: '开发', link: '/docs/development/README' },
    ],
    sidebar: [
      {
        text: '项目与导航',
        items: [
          { text: '项目介绍', link: '/project' },
          { text: '更新日志', link: '/docs/changelog' },
          { text: '文档导航', link: '/docs/README' },
        ],
      },
      {
        text: '界面使用',
        items: [
          { text: '使用说明', link: '/docs/gui/usage' },
        ],
      },
      {
        text: '控制台使用',
        items: [
          { text: '使用说明', link: '/docs/cli-package' },
          { text: '音频筛选', link: '/docs/cli-package#audio-types' },
          { text: '配置文件模式', link: '/docs/api/cli_api#config-file' },
          { text: '完整参数', link: '/docs/api/cli_api' },
        ],
      },
      {
        text: '其他信息',
        items: [
          { text: '音频文件与输出目录', link: '/docs/audio-and-output' },
          { text: '本地游戏目录', link: '/docs/api/prepared_source' },
          { text: '常见问题', link: '/docs/faq' },
        ],
      },
      {
        text: 'API',
        collapsed: true,
        items: [
          { text: 'API 总览', link: '/docs/API' },
          { text: 'Python API', link: '/docs/api/python_api' },
          { text: '配置文件与设置', link: '/docs/api/config_api#config-files' },
          { text: '运行上下文', link: '/docs/api/config_api#app-context' },
          { text: '解包与事件映射', link: '/docs/api/pipeline_api' },
          { text: '模块与数据结构', link: '/docs/api/README' },
          { text: '资源库与索引', link: '/docs/api/library_api' },
        ],
      },
      {
        text: '开发与构建',
        collapsed: true,
        items: [
          { text: '开发文档', link: '/docs/development/README' },
          { text: '音频 ID 与内容实测', link: '/docs/research/historical-wem' },
          { text: '事件名与范围实测', link: '/docs/research/historical-events' },
          { text: '文档网站维护', link: '/docs/development/doc-site' },
          { text: '控制台打包', link: '/docs/development/cli-packaging' },
          { text: '基准与性能', link: '/docs/api/benchmarking_and_performance' },
          { text: '界面数据准备', link: '/docs/gui/shared_entity_data_refresh' },
          { text: '界面任务与导出', link: '/docs/development/gui-tasks-and-exports' },
          { text: '本地源验证合同', link: '/docs/development/prepared-source-contract' },
          { text: '日志治理', link: '/docs/logging/README' },
        ],
      },
    ],
    outline: { level: [2, 3], label: '本页目录' },
    sidebarMenuLabel: '文档目录',
    returnToTopLabel: '回到顶部',
    skipToContentLabel: '跳到正文',
    darkModeSwitchLabel: '主题',
    darkModeSwitchTitle: '切换为深色主题',
    lightModeSwitchTitle: '切换为浅色主题',
    docFooter: { prev: '上一页', next: '下一页' },
    socialLinks: [{ icon: 'github', link: 'https://github.com/Virace/lol_extract_voice' }],
    search: {
      provider: 'local',
      options: {
        miniSearch: {
          options: {
            tokenize: (text) => Array.from(new Intl.Segmenter('zh', { granularity: 'word' }).segment(text))
              .filter((part) => part.isWordLike)
              .map((part) => part.segment),
          },
        },
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: {
            noResultsText: '没有找到相关内容',
            resetButtonTitle: '清空搜索',
            displayDetails: '显示详细内容',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },
  },
})
