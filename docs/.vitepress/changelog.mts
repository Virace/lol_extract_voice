import { createMarkdownRenderer, disposeMdItInstance } from 'vitepress'
import { repoRoot } from './source.mts'
import type { ReleaseInfo } from './release.mts'

/** 保留 Release 全文，调整标题层级并生成可搜索、可按版本跳转的静态正文。 */
export async function renderChangelog(info: ReleaseInfo): Promise<string> {
  if (!info.releases?.length) {
    return '暂未取得更新日志，请查看 [GitHub 发行版](https://github.com/Virace/lol_extract_voice/releases)。'
  }

  const md = await createMarkdownRenderer(repoRoot, {
    // 远程正文不能执行 HTML、Vue 表达式或本地文件引入指令。
    html: false,
    include: false,
    snippet: false,
    config(renderer) {
      renderer.core.ruler.before('anchor', 'release-headings', (state) => {
        const tokens = state.tokens
        if (tokens[0]?.type === 'heading_open' && tokens[0].tag === 'h1'
          && tokens[1]?.content.includes(state.env.releaseTag)) {
          tokens.splice(0, 3)
        }
        for (const token of tokens) {
          if (token.type === 'heading_open' || token.type === 'heading_close') {
            token.tag = `h${Math.min(6, Number(token.tag.slice(1)) + 1)}`
          }
          if (token.type !== 'inline') continue
          for (const child of token.children || []) {
            if (child.type !== 'link_open' && child.type !== 'image') continue
            const attr = child.type === 'image' ? 'src' : 'href'
            const href = child.attrGet(attr)
            if (href && !/^(?:[a-z][\w+.-]*:|\/\/)/i.test(href)) {
              child.attrSet(attr, new URL(href, `${state.env.releaseUrl}/`).href)
            }
          }
        }
      })
    },
    anchor: { level: [] },
  })

  const escape = md.utils.escapeHtml
  const date = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
  })
  const sections: string[] = []
  for (const release of info.releases) {
    const body = release.body
      ? await md.renderAsync(release.body, { releaseTag: release.tag, releaseUrl: release.url })
      : '<p>此版本未附更新说明，附件与详情请查看 GitHub 发行版。</p>'
    const id = `release-${release.tag.replace(/[^a-zA-Z0-9-]/g, '-')}`
    const title = release.name === release.tag ? release.tag : `${release.tag} · ${release.name}`
    const latest = release.tag === info.tag ? '<span class="changelog-latest">最新正式版</span>' : ''
    sections.push([
      `## ${escape(title)} {#${id} .changelog-version}`,
      `<div class="changelog-meta" v-pre><time datetime="${escape(release.publishedAt)}">${date.format(new Date(release.publishedAt))}</time>${latest}<a href="${escape(release.url)}" target="_blank" rel="noreferrer">查看发行版 ↗</a></div>`,
      `<div class="changelog-body" v-pre>\n${body}\n</div>`,
    ].join('\n\n'))
  }
  // VitePress 全局复用渲染器；释放实例，避免这里的设置改变普通文档渲染。
  disposeMdItInstance()
  return sections.join('\n\n')
}
