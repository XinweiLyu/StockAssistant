#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo '请先按 docs/a-share-assistant.md 安装项目依赖。' >&2
  exit 1
fi
export A_SHARE_ASSISTANT_ENABLED=true
exec .venv/bin/python -m uvicorn server:app --host "${WEBUI_HOST:-127.0.0.1}" --port "${WEBUI_PORT:-8000}"
