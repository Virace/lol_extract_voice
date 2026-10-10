import { readFileSync, readdirSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { MarkdownOptions } from 'vitepress'

export const repoRoot = fileURLToPath(new URL('../../', import.meta.url))
export const siteRoot = path.join(repoRoot, '.temp', '.docs-site')

// 导航与 favicon 共用原图标，内联后无需维护或发布额外的静态文件目录。
export const brandIcon = `data:image/svg+xml;base64,${readFileSync(path.join(repoRoot, 'src/lol_audio_unpack/gui/assets/app_icon.svg')).toString('base64')}`

/** 仓库文件链接固定到构建提交；源码归档没有 Git 元数据时明确使用主分支。 */
function resolveRef() {
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  } catch {
    console.warn('[docs] 无法读取 Git 提交，仓库文件链接使用 main 分支。')
    return 'main'
  }
}

const repoFiles = `https://github.com/Virace/lol_extract_voice/blob/${resolveRef()}/`

// 根目录只发布 README，正文继续使用 docs/；新增的仓库目录也默认排除。
export const sourceExcludes = readdirSync(repoRoot)
  .filter((name) => name !== 'README.md' && name !== 'docs')
  .map((name) => `${name}{,/**}`)
  .concat(['docs/.vitepress/**', 'docs/node_modules/**', 'docs/public/**'])

/** 仅在渲染阶段适配仓库链接，Markdown 原文仍可直接在 GitHub 阅读。 */
export const sourceLinks: NonNullable<MarkdownOptions['config']> = (md) => {
  md.core.ruler.after('inline', 'repository-links', (state) => {
    const page = state.env.relativePath || 'index.md'
    for (const block of state.tokens) {
      for (const token of block.children || []) {
        if (token.type !== 'link_open') continue
        const href = token.attrGet('href')
        if (!href || /^(?:[a-z][\w+.-]*:|\/\/|#)/i.test(href)) continue

        const url = new URL(href, `https://docs.invalid/${page}`)
        const file = decodeURIComponent(url.pathname).replace(/^\/+/, '')
        const suffix = `${url.search}${url.hash}`
        if (file === 'README.md') {
          token.attrSet('href', `/project.md${suffix}`)
        } else if (file.startsWith('docs/') && file.endsWith('.md')) {
          token.attrSet('href', `/${file}${suffix}`)
        } else {
          // 配置、规范与许可证使用构建提交的 GitHub 文件页，不复制到网站。
          token.attrSet('href', `${repoFiles}${file}${suffix}`)
        }
      }
    }
  })
}
