#!/usr/bin/env bash
# Unduh source Hermes Agent yang dipin, lalu bundel sebagai aset APK.
#
# --slim : buang direktori yang tidak dibutuhkan runtime (tests, website,
#          contributors, .github, evals, tests-js, nix). apps/ TETAP disertakan
#          agar dashboard/Desktop/TUI source tetap ada. Menghemat ~37 MB.
set -euo pipefail
source "$(dirname "$0")/common.sh"

TAG="v0.23.1"
FORCE=0
SLIM=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --slim) SLIM=1; shift ;;
    -h|--help) echo "usage: $0 [--tag v0.23.1|main] [--force] [--slim]"; exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

need curl
need python3
need tar

if [[ "$TAG" == "main" ]]; then
  URL="https://github.com/NousResearch/hermes-agent/archive/refs/heads/main.tar.gz"
else
  URL="https://github.com/NousResearch/hermes-agent/archive/refs/tags/${TAG}.tar.gz"
fi

DEST="$RUNTIME_ASSET_DIR/hermes-src.tar.gz"
if [[ -f "$DEST" && $FORCE -eq 0 ]]; then
  log "Source Hermes sudah ada ($(du -h "$DEST" | cut -f1)). Pakai --force untuk unduh ulang."
else
  log "Mengunduh Hermes Agent $TAG …"
  curl -fL --retry 3 --retry-delay 2 "$URL" -o "$DEST.tmp"
  gzip -t "$DEST.tmp" || die "unduhan bukan arsip gzip yang valid: $URL"
  mv "$DEST.tmp" "$DEST"
fi

PACK="full"
if [[ $SLIM -eq 1 ]]; then
  PACK="slim"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  log "Membuat paket runtime-slim (tanpa tests/website/contributors/.github/evals/tests-js/nix) …"
  mkdir -p "$TMP/root"
  # Ekstraksi dengan --exclude: berkas berat tidak pernah ditulis ke disk.
  # apps/ sengaja TETAP disertakan agar source dashboard/Desktop/TUI ada.
  EXCLUDES=()
  for d in tests website contributors .github evals tests-js nix; do
    EXCLUDES+=(--exclude="hermes-agent-*/$d" --exclude="hermes-agent-*/$d/*")
  done
  tar -xzf "$DEST" -C "$TMP/root" "${EXCLUDES[@]}"
  ROOT="$(find "$TMP/root" -maxdepth 1 -mindepth 1 -type d -print -quit)"
  [[ -n "$ROOT" ]] || die "direktori akar source tidak ditemukan di dalam arsip"
  (cd "$TMP/root" && tar -czf "$DEST.slim" "$(basename "$ROOT")")
  mv "$DEST.slim" "$DEST"
  log "Paket slim: $(du -h "$DEST" | cut -f1) (hemat dari arsip penuh)"
fi

SHA="$(sha256_file "$DEST")"
manifest_set_hermes_sha "$TAG" "$SHA" "$PACK"
python3 - "$MANIFEST" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["hermesSrc"]["slimExcludes"] = ["tests", "website", "contributors", ".github", "evals", "tests-js", "nix"]
d["hermesSrc"]["note"] = "apps/, agent/, tools/, gateway/, hermes_cli/, skills/, plugins/, optional-skills/ tetap disertakan"
with open(p, "w", encoding="utf-8") as fh:
    json.dump(d, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY
log "Source Hermes $TAG ($PACK) dibundel: $(du -h "$DEST" | cut -f1), sha256=$SHA"
