import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { siteRoot } from './source.mts'

export interface ReleaseInfo {
  fetchedAt?: string
  tag?: string
  publishedAt?: string
  updatedAt?: string
  url: string
}

const latest = 'https://github.com/Virace/lol_extract_voice/releases/latest'
const cacheFile = path.join(siteRoot, 'release.json')

/** 构建时读取发布信息；CI 要求最新数据，本地离线时保留下载入口。 */
export async function loadRelease(): Promise<ReleaseInfo> {
  const fresh = process.env.CI === 'true'
  let cached: ReleaseInfo | undefined
  try {
    cached = JSON.parse(readFileSync(cacheFile, 'utf8'))
    if (!fresh && cached?.fetchedAt && cached.updatedAt && Date.now() - Date.parse(cached.fetchedAt) < 3_600_000) return cached
  } catch { /* 首次构建尚无本地缓存。 */ }

  try {
    // 令牌只在构建进程中使用，页面仅接收下方 ReleaseInfo 的公开字段。
    const headers: Record<string, string> = {
      Accept: 'application/vnd.github+json',
      'User-Agent': 'lol-audio-unpack-docs',
      'X-GitHub-Api-Version': '2022-11-28',
    }
    if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`
    const response = await fetch('https://api.github.com/repos/Virace/lol_extract_voice/releases/latest', {
      headers,
      signal: AbortSignal.timeout(8000),
    })
    if (!response.ok) throw new Error(`GitHub HTTP ${response.status}`)
    const release = await response.json()
    const info: ReleaseInfo = {
      fetchedAt: new Date().toISOString(),
      tag: release.tag_name,
      publishedAt: release.published_at,
      updatedAt: release.updated_at,
      url: release.html_url,
    }
    mkdirSync(siteRoot, { recursive: true })
    writeFileSync(cacheFile, `${JSON.stringify(info, null, 2)}\n`)
    return info
  } catch (error) {
    if (fresh) throw new Error(`[docs] 无法获取最新 Release 信息，停止发布：${error}`)
    console.warn(`[docs] Release 信息获取失败，${cached ? '沿用缓存' : '使用发布页入口'}：${error}`)
    return cached || { url: latest }
  }
}
