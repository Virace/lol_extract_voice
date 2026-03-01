#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

chmod +x .githooks/pre-commit
git config core.hooksPath .githooks

echo "Git hooks 已启用: .githooks"
echo "已启用检查: 提交前自动校验版本后缀"
