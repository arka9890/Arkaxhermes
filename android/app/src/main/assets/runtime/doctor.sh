#!/bin/bash
# Pemeriksaan lingkungan proot. Output "ARKAX:log:" dipetakan ke SSE.
set -uo pipefail

info() { printf 'ARKAX:log:%s\n' "$*"; }
good() { info "OK   $*"; }
bad()  { info "WARN $*"; }

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then good "$label"; else bad "$label tidak tersedia"; fi
}

info "=== Arkaxhermes doctor ($(date -u +%FT%TZ)) ==="
info "uname: $(uname -a)"
info "python: $(python3 --version 2>&1 | head -n1)"
info "node:   $(node --version 2>&1 | head -n1)"
info "hermes: $(hermes --version 2>&1 | head -n1)"
info "disk:   $(df -h / | tail -n1 | awk '{print $4" free / "$2" total"}')"
info "DNS:    $(getent hosts api.github.com >/dev/null 2>&1 && echo resolv-ok || echo resolv-failed)"

check "bash"      bash --version
check "git"       git --version
check "curl"      curl --version
check "python3"   python3 --version
check "node"      node --version
check "pip"       python3 -m pip --version
check "hermes"    hermes --version
check "sqlite3"   sqlite3 --version
check "ffmpeg"    ffmpeg -version
check "agent-browser CLI" /usr/local/bin/agent-browser --version
check "Chrome headless-shell" test -x /mnt/arkax/browser/chrome-wrapper.sh
info "Stream browser: ws://127.0.0.1:9223 · Dashboard: http://127.0.0.1:4848"
check "ripgrep"   rg --version
check "resolv.conf" test -s /etc/resolv.conf
check "HERMES_HOME" test -d "${HERMES_HOME:-/root/.hermes}"

if [[ -x /usr/local/bin/hermes ]]; then
  info "--- hermes doctor (upstream) ---"
  hermes doctor 2>&1 | sed 's/^/ARKAX:log:/' || bad "hermes doctor mengembalikan error"
else
  bad "/usr/local/bin/hermes tidak ada — jalankan install-hermes.sh"
fi

info "=== selesai ==="
exit 0
