#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "未检测到 uv，请先安装 uv。" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "未检测到 Python（python3/python）。" >&2
  exit 1
fi

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${ROOT_DIR}/.venv-wsl}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${ROOT_DIR}/.cache}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${ROOT_DIR}/.config}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-${ROOT_DIR}/.state}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME}/uv}"

ensure_dirs() {
  mkdir -p "${UV_PROJECT_ENVIRONMENT}" "${XDG_CACHE_HOME}" "${XDG_CONFIG_HOME}" "${XDG_STATE_HOME}" "${UV_CACHE_DIR}"
}

print_usage() {
  cat <<EOF
用法:
  ./scripts/_uv.sh init [uv sync 参数...]
  ./scripts/_uv.sh <uv 子命令> [参数...]

示例:
  ./scripts/_uv.sh init
  ./scripts/_uv.sh run pytest -q
  ./scripts/_uv.sh sync --group dev

默认环境变量（可被外部覆盖）:
  UV_PROJECT_ENVIRONMENT=${ROOT_DIR}/.venv-wsl
  XDG_CACHE_HOME=${ROOT_DIR}/.cache
  XDG_CONFIG_HOME=${ROOT_DIR}/.config
  XDG_STATE_HOME=${ROOT_DIR}/.state
  UV_CACHE_DIR=${ROOT_DIR}/.cache/uv
EOF
}

cmd="${1:-}"
case "${cmd}" in
  ""|-h|--help|help)
    print_usage
    ;;
  init)
    shift
    ensure_dirs
    if [[ ! -x "${UV_PROJECT_ENVIRONMENT}/bin/python" ]]; then
      echo "创建虚拟环境: ${UV_PROJECT_ENVIRONMENT}"
      uv venv "${UV_PROJECT_ENVIRONMENT}" --python "${PYTHON_BIN}"
    fi

    echo "同步依赖到 ${UV_PROJECT_ENVIRONMENT}"
    uv sync \
      --active \
      --group dev \
      --python "${PYTHON_BIN}" \
      --no-managed-python \
      --no-python-downloads \
      "$@"

    echo "完成。可使用以下命令进入环境："
    echo "source ${UV_PROJECT_ENVIRONMENT}/bin/activate"
    ;;
  *)
    ensure_dirs
    uv "$@"
    ;;
esac
