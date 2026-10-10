import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { siteRoot } from './source.mts'

export interface ReleaseInfo {
  fetchedAt?: string
  tag?: string
  publishedAt?: string
  updatedAt?: string
  url: string
  releases?: ReleaseNotes[]
}

export interface ReleaseNotes {
  tag: string
  name: string
  publishedAt: string
  updatedAt: string
  url: string
  body: string
}

interface GitHubRelease {
  tag_name: string
  name: string | null
  published_at: string
  updated_at: string
  html_url: string
  body: string | null
  draft: boolean
  prerelease: boolean
}

export const releaseLimit = 5
const endpoint = 'repos/Virace/lol_extract_voice/releases'
const latest = 'https://github.com/Virace/lol_extract_voice/releases/latest'
const cacheFile = path.join(siteRoot, 'release.json')

function readGitHub<T>(resource: string): T {
  return JSON.parse(execFileSync('gh', ['api', resource], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 30_000,
    maxBuffer: 8 * 1024 * 1024,
  }))
}

/** 构建时通过 gh 读取正式版信息；CI 获取失败时停止发布，本地允许使用缓存。 */
export async function loadRelease(): Promise<ReleaseInfo> {
  const fresh = process.env.CI === 'true'
  let cached: ReleaseInfo | undefined
  try {
    cached = JSON.parse(readFileSync(cacheFile, 'utf8'))
    if (!fresh && cached?.fetchedAt && cached.updatedAt && cached.releases && Date.now() - Date.parse(cached.fetchedAt) < 3_600_000) return cached
  } catch { /* 首次构建尚无本地缓存。 */ }

  try {
    // gh 使用本机登录或 workflow 的 GITHUB_TOKEN，缓存只保存筛选后的公开字段。
    const release = readGitHub<GitHubRelease>(`${endpoint}/latest`)
    const releases: GitHubRelease[] = []
    for (let page = 1; releases.length < releaseLimit; page++) {
      const batch = readGitHub<GitHubRelease[]>(`${endpoint}?per_page=30&page=${page}`)
      releases.push(...batch.filter((item) => !item.draft && !item.prerelease))
      if (batch.length < 30) break
    }
    const info: ReleaseInfo = {
      fetchedAt: new Date().toISOString(),
      tag: release.tag_name,
      publishedAt: release.published_at,
      updatedAt: release.updated_at,
      url: release.html_url,
      releases: releases
        .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at))
        .slice(0, releaseLimit)
        .map((item) => ({
          tag: item.tag_name,
          name: item.name || item.tag_name,
          publishedAt: item.published_at,
          updatedAt: item.updated_at,
          url: item.html_url,
          body: item.body || '',
        })),
    }
    mkdirSync(siteRoot, { recursive: true })
    writeFileSync(cacheFile, `${JSON.stringify(info, null, 2)}\n`)
    return info
  } catch (error) {
    if (fresh) throw new Error(`[docs] 无法通过 gh 获取正式版发布信息，停止发布：${error}`)
    console.warn(`[docs] gh 获取发布信息失败，${cached ? '沿用缓存' : '使用发布页入口'}：${error}`)
    return cached || { url: latest }
  }
}
