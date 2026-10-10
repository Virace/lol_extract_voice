import { readFileSync } from 'node:fs'
import path from 'node:path'
import { repoRoot } from './source.mts'

/** 首页只读取 README 的简介和能力列表，正文始终由原文件维护。 */
export function readProject() {
  const readme = readFileSync(path.join(repoRoot, 'README.md'), 'utf8')
  const summary = readme.match(/<!-- project-summary -->\s*([\s\S]*?)\s*<!-- \/project-summary -->/)?.[1].trim()
  const features = [...readme.matchAll(/^- \*\*(.+?)\*\*：(.+)$/gm)]
    .map((match) => ({ title: match[1], details: match[2] }))
  if (!summary || !features.length) throw new Error('README 缺少首页共用简介或能力列表。')
  return { name: readme.match(/^# (.+)$/m)![1], summary, features }
}
