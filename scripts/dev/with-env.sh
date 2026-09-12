#!/bin/sh
set -eu
REHEARSAL_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export PATH="$REHEARSAL_ROOT/.tooling/node/bin:$PATH"
export UV_CACHE_DIR="$REHEARSAL_ROOT/.tooling/uv-cache"
export UV_PYTHON_INSTALL_DIR="$REHEARSAL_ROOT/.tooling/python"
export UV_PYTHON_PREFERENCE=only-managed
export UV_PROJECT_ENVIRONMENT="$REHEARSAL_ROOT/.venv"
export npm_config_cache="$REHEARSAL_ROOT/.tooling/npm-cache"
export npm_config_update_notifier=false
export PLAYWRIGHT_BROWSERS_PATH="$REHEARSAL_ROOT/.tooling/browsers"
export MEDUSA_DISABLE_TELEMETRY=true
export DO_NOT_TRACK=1
export XDG_CONFIG_HOME="$REHEARSAL_ROOT/.local/config"
export XDG_CACHE_HOME="$REHEARSAL_ROOT/.local/cache"
cd "$REHEARSAL_ROOT"
if [ ! -x "$REHEARSAL_ROOT/.tooling/node/bin/node" ]; then
  echo 'Missing pinned runtime. Run make setup-tooling.' >&2
  exit 1
fi
exec "$@"
