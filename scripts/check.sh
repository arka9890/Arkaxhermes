#!/usr/bin/env bash
# Validasi repo tanpa Android SDK. Dipakai CI dan sebelum commit.
set -euo pipefail
source "$(dirname "$0")/common.sh"

FAIL=0
ok()   { printf '  \033[1;32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[1;31mFAIL\033[0m %s\n' "$*"; FAIL=1; }
skip() { printf '  \033[1;33mSKIP\033[0m %s\n' "$*"; }

log "1. Sintaks shell"
for f in "$ARKAX_ROOT"/scripts/*.sh "$RUNTIME_ASSET_DIR"/*.sh; do
  [[ -f "$f" ]] || continue
  if bash -n "$f"; then ok "$(basename "$f")"; else bad "$(basename "$f")"; fi
done

log "2. Sintaks Python"
PY_TMP="$(mktemp -d)"
trap 'rm -rf "$PY_TMP"' EXIT
for f in "$RUNTIME_ASSET_DIR"/*.py "$ARKAX_ROOT"/scripts/*.py; do
  [[ -f "$f" ]] || continue
  if PYTHONPYCACHEPREFIX="$PY_TMP/pycache" python3 -m py_compile "$f"; then ok "$(basename "$f")"; else bad "$(basename "$f")"; fi
done

log "3. Sintaks JavaScript UI"
if command -v node >/dev/null 2>&1; then
  JS="$PY_TMP/arkax-ui.js"
  python3 - "$ASSET_ROOT/www/index.html" "$JS" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8").read()
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.S | re.I)
if not scripts:
    raise SystemExit("tidak ada blok <script> di index.html")
open(sys.argv[2], "w", encoding="utf-8").write("\n;\n".join(scripts))
print(f"{len(scripts)} blok script, {sum(len(s) for s in scripts)} karakter")
PY
  if node --check "$JS"; then ok "index.html: JavaScript valid"; else bad "JavaScript index.html"; fi
else
  skip "node tidak tersedia"
fi

log "4. JSON"
if python3 - "$MANIFEST" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
assert len(m["ubuntu"]["architectures"]["arm64"]["sha256"]) == 64
assert len(m["ubuntu"]["architectures"]["amd64"]["sha256"]) == 64
assert m["hermesSrc"]["repository"].startswith("https://github.com/")
print("manifest valid")
PY
then ok "rootfs/manifest.json"; else bad "rootfs/manifest.json"; fi

log "5. Berkas wajib"
REQUIRED=(
  "README.md" "LICENSE" "CHANGELOG.md"
  "docs/ARCHITECTURE.md" "docs/BUILD.md" "docs/BRIDGE_API.md"
  "docs/FEATURE_MAP.md" "docs/PROOTFS.md"
  "android/settings.gradle.kts" "android/build.gradle.kts"
  "android/app/build.gradle.kts"
  "android/app/src/main/AndroidManifest.xml"
  "android/app/src/main/java/com/arkaxhermes/app/MainActivity.kt"
  "android/app/src/main/java/com/arkaxhermes/app/bridge/ArkaxHttpServer.kt"
  "android/app/src/main/java/com/arkaxhermes/app/runtime/ProotRuntime.kt"
  "android/app/src/main/java/com/arkaxhermes/app/runtime/RootfsInstaller.kt"
  "android/app/src/main/java/com/arkaxhermes/app/runtime/HermesRuntime.kt"
  "android/app/src/main/assets/www/index.html"
  "android/app/src/main/assets/runtime/hermes_bridge.py"
  "android/app/src/main/assets/runtime/bootstrap.sh"
  "android/app/src/main/assets/runtime/install-hermes.sh"
  "android/app/src/main/assets/runtime/agent-browser-wrapper.sh"
  "android/app/src/main/assets/runtime/browser-bootstrap.sh"
  "android/app/src/main/java/com/arkaxhermes/app/runtime/BrowserRuntime.kt"
)
for f in "${REQUIRED[@]}"; do
  if [[ -f "$ARKAX_ROOT/$f" ]]; then ok "$f"; else bad "$f (hilang)"; fi
done

log "6. Konsistensi dokumen"
if grep -q 'Arkaxhermes' "$ARKAX_ROOT/README.md" && grep -q 'v0.23.1' "$ARKAX_ROOT/README.md"; then
  ok "README menyebut nama repo & pin upstream"
else
  bad "README tidak konsisten"
fi
if grep -q 'tidung\|menolang' "$ARKAX_ROOT"/docs/*.md 2>/dev/null; then
  bad "ada typo yang diketahui di docs/"
else
  ok "tidak ada typo yang diketahui"
fi

log "7. Aset biner (informasional, tidak menggagalkan CI)"
[[ -f "$ROOTFS_ASSET_DIR/rootfs.sha256" ]] && ok "rootfs.sha256 ada" || skip "rootfs belum dibuat (scripts/make-assets.sh)"
[[ -f "$JNILIBS_DIR/arm64-v8a/libproot.so" ]] && ok "libproot.so ada" || skip "libproot.so belum ada"
[[ -f "$JNILIBS_DIR/arm64-v8a/libagent-browser.so" ]] && ok "libagent-browser.so ada" || skip "libagent-browser.so belum ada"
[[ -f "$ARKAX_ROOT/dist/chrome-headless-shell-linux-arm64.zip" ]] && ok "Chrome for Testing ZIP ada di dist/ (distagel saat build)" || skip "Chrome ZIP akan diunduh saat build APK"
[[ -f "$RUNTIME_ASSET_DIR/hermes-src.tar.gz" ]] && ok "source Hermes ada" || skip "source Hermes belum ada"

log "8. Audit UI / CLI / API terhadap Hermes v0.23.1"
if command -v node >/dev/null 2>&1; then
  if python3 "$ARKAX_ROOT/scripts/audit.py" --strict > "$PY_TMP/audit.log" 2>&1; then
    ok "audit.py: $(head -n1 "$PY_TMP/audit.log")"
  else
    bad "audit.py menemukan ketidaksesuaian"
    sed 's/^/       /' "$PY_TMP/audit.log"
  fi
else
  skip "node tidak tersedia (audit UI dilewati)"
fi

printf '\n'
if [[ $FAIL -eq 0 ]]; then
  log "Semua pemeriksaan lulus ✅"
else
  die "Ada pemeriksaan yang gagal ❌"
fi
