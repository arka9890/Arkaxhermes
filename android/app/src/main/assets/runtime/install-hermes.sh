#!/bin/bash
# Pasang Hermes Agent (NousResearch/hermes-agent) di dalam Ubuntu proot.
# Offline-first: memakai /opt/arkax/hermes-src.tar.gz yang dibundel di APK.
set -euo pipefail

SRC="/opt/arkax/hermes-src.tar.gz"
DEST="/opt/hermes-agent"
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
HERMES_TAG="${HERMES_TAG:-v0.23.1}"
VERBOSE="${1:-}"

info() { printf 'ARKAX:log:%s\n' "$*"; }
info "install-hermes.sh: tag=$HERMES_TAG src=$([[ -f "$SRC" ]] && echo bundled || echo network)"

if [[ "${ARKAX_USE_INSTALLER:-0}" == "1" ]]; then
  info "Menggunakan installer resmi (ARKAX_USE_INSTALLER=1) …"
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
else
  if [[ -f "$SRC" ]]; then
    info "Mengekstrak source Hermes yang dibundel …"
    rm -rf "$DEST.tmp" && mkdir -p "$DEST.tmp"
    tar -xzf "$SRC" -C "$DEST.tmp" --strip-components=1
    rm -rf "$DEST" && mv "$DEST.tmp" "$DEST"
  else
    info "Source bundel tidak ada; clone dari GitHub $HERMES_TAG …"
    rm -rf "$DEST"
    git clone --depth 1 --branch "$HERMES_TAG" \
      https://github.com/NousResearch/hermes-agent.git "$DEST"
  fi

  cd "$DEST"
  # Hermes upstream memakai uv untuk mengelola environment Python; fallback ke venv+pip.
  if command -v uv >/dev/null 2>&1; then
    info "uv ditemukan: uv sync"
    uv sync --frozen 2>/dev/null || uv sync || {
      info "uv sync gagal, fallback python3 -m venv + pip install -e ."
      python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -e .
    }
  elif [[ -f pyproject.toml ]]; then
    info "python3 -m venv + pip install -e ."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
  else
    info "pyproject.toml tidak ada — memakai installer resmi sebagai fallback"
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  fi
fi

# Cari entrypoint CLI hasil instalasi.
BIN=""
for candidate in \
  "$DEST/.venv/bin/hermes" \
  "$HERMES_HOME/bin/hermes" \
  "$(command -v hermes 2>/dev/null || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then BIN="$candidate"; break; fi
done

if [[ -n "$BIN" && "$BIN" != /usr/local/bin/hermes ]]; then
  cat > /usr/local/bin/hermes <<EOF
#!/bin/sh
# Arkaxhermes wrapper — Hermes Agent dari source $HERMES_TAG
export HERMES_HOME="$HERMES_HOME"
exec "$BIN" "\$@"
EOF
  chmod 755 /usr/local/bin/hermes
elif [[ -z "$BIN" ]]; then
  # Fallback terakhir: modul CLI ada di source tree.
  cat > /usr/local/bin/hermes <<EOF
#!/bin/sh
export HERMES_HOME="$HERMES_HOME"
export PYTHONPATH="$DEST\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$DEST/.venv/bin/python" -m hermes_cli "\$@"
EOF
  chmod 755 /usr/local/bin/hermes
  info "PERINGATAN: biner hermes tidak ditemukan; wrapper memakai python -m hermes_cli"
fi

mkdir -p "$HERMES_HOME"/{skills,logs,run,cron,plugins,hooks,profiles,trajectories,context,backups}
[[ -f "$HERMES_HOME/.env" ]] || { touch "$HERMES_HOME/.env"; chmod 600 "$HERMES_HOME/.env"; }
[[ -f "$HERMES_HOME/config.yaml" ]] || cat > "$HERMES_HOME/config.yaml" <<'YAML'
# Arkaxhermes default — dijalankan di dalam Ubuntu proot.
agent:
  max_turns: 90
terminal:
  backend: local
  cwd: /mnt/arkax/scripts
  timeout: 180
YAML

if [[ "$VERBOSE" == "--verbose" ]]; then
  info "python=$(python3 --version 2>&1) node=$(node --version 2>&1 | head -n1)"
  info "hermes=$(hermes --version 2>&1 | head -n1)"
  info "doctor:"; hermes doctor 2>&1 | sed 's/^/ARKAX:log:/' || true
else
  hermes --version >/dev/null 2>&1 || info "PERINGATAN: hermes --version gagal; cek /api/logs"
fi

info "Hermes Agent siap di $DEST ($HERMES_TAG)"
