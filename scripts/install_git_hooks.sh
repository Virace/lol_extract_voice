#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

chmod +x .githooks/pre-commit
chmod +x .githooks/pre-merge-commit
chmod +x .githooks/post-checkout
git config core.hooksPath .githooks

echo "Git hooks 已启用: .githooks"
echo "已启用检查: 提交前版本后缀校验 + main 本地依赖校验"
echo "已启用提示: 切换分支时若进入 main/master 且存在本地依赖，会打印警告"
