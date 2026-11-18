#!/bin/bash
# Dijalankan SEKALI oleh RootfsInstaller/ProotRuntime setelah rootfs diekstrak.
# Semua output berawalan "ARKAX:" dipetakan ArkaxHttpServer ke SSE progress/log.
set -euo pipefail

ARKAX_STATE=/etc/arkax
HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
mkdir -p "$ARKAX_STATE" "$HERMES_HOME"/{skills,logs,run,cron,plugins,hooks,profiles,trajectories,approvals,context,backups} \
         /mnt/arkax/{inbox,exports,scripts} /opt/hermes-agent

step() { printf 'ARKAX:step:%s:%s:%s\n' "$1" "$2" "$3"; }
info() { printf 'ARKAX:log:%s\n' "$*"; }

step setup 5 "Menyiapkan identitas & DNS Ubuntu"
printf 'arkaxhermes\n' > /etc/hostname
grep -q 'arkaxhermes' /etc/hosts || printf '127.0.0.1 localhost arkaxhermes\n' >> /etc/hosts
if [[ ! -s /etc/resolv.conf ]]; then
  printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > /etc/resolv.conf
fi
printf 'LANG=C.UTF-8\nLC_ALL=C.UTF-8\n' > /etc/default/locale 2>/dev/null || true
export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

if [[ ! -f "$ARKAX_STATE/deps.done" ]]; then
  step packages 15 "apt-get update"
  info "Memasang dependency: python3, nodejs, git, curl, ffmpeg, ripgrep, sqlite3"
  apt-get update -qq || info "apt-get update gagal, mencoba melanjutkan dengan paket yang sudah ada"
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git curl ca-certificates \
    nodejs npm ripgrep ffmpeg tzdata locales procps sqlite3 \
    || info "Sebagian paket gagal dipasang; install-hermes.sh akan mencoba lagi"
  apt-get clean
  rm -rf /var/lib/apt/lists/*
  touch "$ARKAX_STATE/deps.done"
fi

# uv tidak ada di repo Ubuntu 24.04, padahal Hermes membutuhkannya: dependency
# intinya di-gate `python_version >= '3.14'` dan Python 3.14 dipasang lewat
# `uv python install`. Dipasang di luar guard deps.done supaya rootfs lama pun
# ikut mendapatkannya.
if ! command -v uv >/dev/null 2>&1; then
  info "Memasang uv (manajer Python untuk Hermes) …"
  python3 -m pip install --break-system-packages -q uv \
    || info "pip install uv gagal; install-hermes.sh akan memakai venv python3 sistem"
fi

step hermes 45 "Memasang Hermes Agent dari source bundel"
bash /opt/arkax/install-hermes.sh

step env 80 "Menyiapkan ~/.hermes"
if [[ -f /mnt/arkax/secrets.env ]]; then
  # Kunci API dikirim Kotlin → berkas ini, tidak pernah lewat localStorage WebView.
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    key="${line%%=*}"
    if grep -q "^${key}=" "$HERMES_HOME/.env" 2>/dev/null; then
      sed -i "s|^${key}=.*|${line}|" "$HERMES_HOME/.env"
    else
      printf '%s\n' "$line" >> "$HERMES_HOME/.env"
    fi
  done < /mnt/arkax/secrets.env
  chmod 600 "$HERMES_HOME/.env"
  shred -u /mnt/arkax/secrets.env 2>/dev/null || rm -f /mnt/arkax/secrets.env
fi
chmod 700 "$HERMES_HOME"
touch "$HERMES_HOME/.env" && chmod 600 "$HERMES_HOME/.env"

step browser 88 "Memasang agent-browser + Chrome for Testing"
bash /opt/arkax/browser-bootstrap.sh || info "Browser bawaan belum siap — tab Browser akan menampilkan status"

step doctor 92 "hermes doctor"
bash /opt/arkax/doctor.sh || info "doctor menemukan peringatan — lihat layar Log & Doctor"

printf '%s\n' "$(date -u +%FT%TZ)" > "$ARKAX_STATE/first-run.done"
printf '%s\n' "${HERMES_TAG:-bundled}" > "$ARKAX_STATE/hermes-tag"
step ready 100 "Arkaxhermes siap — Hermes Agent berjalan di Ubuntu proot"
info "HOME=$HERMES_HOME  ARCH=$(uname -m)  KERNEL=$(uname -r)"
