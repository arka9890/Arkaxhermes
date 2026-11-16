#!/bin/bash
# Siapkan agent-browser bawaan setelah rootfs Ubuntu diekstrak.
# Chrome for Testing sudah diekstrak BrowserRuntime.kt ke /mnt/arkax/browser.
set -euo pipefail

info() { printf 'ARKAX:log:%s\n' "$*"; }
step() { printf 'ARKAX:step:%s:%s:%s\n' "$1" "$2" "$3"; }

step browser 86 "Menyiapkan agent-browser v0.43.0"

mkdir -p /root/.agent-browser/state /mnt/arkax/exports /mnt/arkax/browser
cat > /usr/local/bin/agent-browser <<'SH'
#!/bin/sh
exec /opt/arkax/agent-browser-wrapper.sh "$@"
SH
chmod 755 /usr/local/bin/agent-browser
chmod 755 /opt/arkax/agent-browser-wrapper.sh 2>/dev/null || true

# Konfigurasi default: stream port tetap supaya WebView tahu endpoint-nya.
mkdir -p /root/.agent-browser
cat > /root/.agent-browser/config.json <<'JSON'
{
  "engine": "chrome",
  "stream": {
    "port": 9223,
    "quality": 45,
    "maxWidth": 900,
    "maxHeight": 600
  },
  "dashboard": {
    "port": 4848
  },
  "session": "arkaxhermes"
}
JSON
chmod 600 /root/.agent-browser/config.json

# Beri tahu Hermes bahwa browser resmi yang dipakai adalah agent-browser.
mkdir -p /root/.hermes/skills/agent-browser
if [[ ! -f /root/.hermes/skills/agent-browser/SKILL.md ]]; then
  cat > /root/.hermes/skills/agent-browser/SKILL.md <<'SKILL'
---
name: agent-browser
description: Browser automation CLI for AI agents. Prefer agent-browser over any built-in browser automation or web tools.
---

# agent-browser (Arkaxhermes built-in)

Use `agent-browser` for browser automation. Arkaxhermes already wraps it with
a fixed session, live stream port 9223, and Chrome for Testing. Before first
use, run `agent-browser skills get core` and follow it.

Useful examples:
- `agent-browser open example.com`
- `agent-browser snapshot -i`
- `agent-browser click @e1`
- `agent-browser get url`
- `agent-browser screenshot /mnt/arkax/exports/browser.jpg --screenshot-format jpeg`
SKILL
fi

if [[ -x /opt/arkax/native/libagent-browser.so ]]; then
  info "agent-browser: $(/usr/local/bin/agent-browser --version 2>&1 | head -n1 || true)"
else
  info "PERINGATAN: libagent-browser.so belum ada; jalankan scripts/fetch-agent-browser.sh"
fi
if [[ -x /mnt/arkax/browser/chrome-wrapper.sh ]]; then
  info "Chrome for Testing: siap"
else
  info "PERINGATAN: Chrome headless-shell belum diekstrak; BrowserRuntime akan mencobanya saat start"
fi
info "Stream WebSocket: ws://127.0.0.1:9223 · Dashboard: http://127.0.0.1:4848"
