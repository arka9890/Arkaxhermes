#!/bin/sh
# Wrapper agent-browser v0.43.0 di dalam Ubuntu proot Arkaxhermes.
#
# Binary CLI ada di nativeLibraryDir Android (dibind ke /opt/arkax/native),
# bukan di filesDir, supaya tetap bisa dieksekusi pada Android 10+.
# Chrome for Testing diekstrak BrowserRuntime.kt ke /mnt/arkax/browser.
set -eu

export HOME=/root
export HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
export AGENT_BROWSER_SESSION="${AGENT_BROWSER_SESSION:-arkaxhermes}"
export AGENT_BROWSER_STREAM_PORT="${AGENT_BROWSER_STREAM_PORT:-9223}"
export AGENT_BROWSER_STREAM_QUALITY="${AGENT_BROWSER_STREAM_QUALITY:-45}"
export AGENT_BROWSER_STREAM_MAX_WIDTH="${AGENT_BROWSER_STREAM_MAX_WIDTH:-900}"
export AGENT_BROWSER_STREAM_MAX_HEIGHT="${AGENT_BROWSER_STREAM_MAX_HEIGHT:-600}"
export AGENT_BROWSER_DASHBOARD_PORT="${AGENT_BROWSER_DASHBOARD_PORT:-4848}"
export AGENT_BROWSER_EXECUTABLE_PATH="${AGENT_BROWSER_EXECUTABLE_PATH:-/mnt/arkax/browser/chrome-wrapper.sh}"
export AGENT_BROWSER_CONFIG="${AGENT_BROWSER_CONFIG:-/root/.agent-browser/config.json}"
export AGENT_BROWSER_STATE_DIR="${AGENT_BROWSER_STATE_DIR:-/root/.agent-browser/state}"

mkdir -p "$(dirname "$AGENT_BROWSER_CONFIG")" "$AGENT_BROWSER_STATE_DIR" /mnt/arkax/exports

AB_BIN="/opt/arkax/native/libagent-browser.so"
[[ -x "$AB_BIN" ]] || {
  echo "agent-browser binary tidak ada: $AB_BIN" >&2
  exit 127
}

# --args dipakai karena Chrome for Testing di proot Android non-root tidak boleh
# memakai sandbox SUID, /dev/shm sering kecil, dan GPU tidak tersedia.
exec "$AB_BIN" \
  --json \
  --session "$AGENT_BROWSER_SESSION" \
  --executable-path "$AGENT_BROWSER_EXECUTABLE_PATH" \
  --args "--no-sandbox,--disable-dev-shm-usage,--disable-gpu,--disable-software-rasterizer,--hide-scrollbars" \
  "$@"
