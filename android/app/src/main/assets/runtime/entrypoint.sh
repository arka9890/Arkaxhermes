#!/bin/bash
# Entrypoint umum: dipanggil ProotRuntime untuk setiap perintah.
# Pemanggilan: /bin/bash /opt/arkax/entrypoint.sh <argv...>
set -euo pipefail

export HOME=/root
export HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM="${TERM:-xterm-256color}"
export ARKAX_NATIVE=1
export ARKAX_ROOTFS=/root
export PYTHONDONTWRITEBYTECODE=1
export UV_CACHE_DIR="${UV_CACHE_DIR:-/root/.cache/uv}"

mkdir -p "$HERMES_HOME"/{logs,run,skills,cron,plugins,hooks,profiles,trajectories,context,backups} \
         /mnt/arkax/{inbox,exports,scripts}

# Hermes memuat ~/.hermes/.env sendiri; jangan pernah mencetak isinya ke log.
if [[ -f "$HERMES_HOME/.env" ]]; then chmod 600 "$HERMES_HOME/.env"; fi

if [[ $# -eq 0 ]]; then
  exec /bin/bash -lc 'echo "Arkaxhermes Ubuntu proot — tidak ada perintah."; exec /bin/bash'
fi

exec "$@"
