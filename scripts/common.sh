#!/usr/bin/env bash
# Fungsi bersama untuk seluruh skrip build Arkaxhermes.
set -euo pipefail

ARKAX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANDROID_DIR="$ARKAX_ROOT/android"
ASSET_ROOT="$ANDROID_DIR/app/src/main/assets"
RUNTIME_ASSET_DIR="$ASSET_ROOT/runtime"
ROOTFS_ASSET_DIR="$ASSET_ROOT/rootfs"
JNILIBS_DIR="$ANDROID_DIR/app/src/main/jniLibs"
MANIFEST="$ARKAX_ROOT/rootfs/manifest.json"

log()  { printf '\033[1;34m[arkax]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "butuh '$1' di PATH"; }

# Membaca nilai dari manifest memakai Python stdlib (jq tidak wajib).
manifest_get() {
  python3 - "$MANIFEST" "$@" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
node = data
for part in sys.argv[2].split("."):
    if part.isdigit():
        node = node[int(part)]
    else:
        node = node[part]
if node is None:
    print("")
else:
    print(node if isinstance(node, str) else json.dumps(node))
PY
}

manifest_set_hermes_sha() {
  python3 - "$MANIFEST" "$1" "$2" "${3:-full}" <<'PY'
import json, sys
path, tag, sha, pack = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["hermesSrc"]["tag"] = tag
data["hermesSrc"]["sha256"] = sha
data["hermesSrc"]["pack"] = pack
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY
}

sha256_file() { sha256sum "$1" | awk '{print $1}'; }

verify_sha256() {
  local file="$1" expected="$2"
  local actual
  actual="$(sha256_file "$file")"
  [[ "$actual" == "$expected" ]] || die "SHA-256 tidak cocok untuk $file\n  expected: $expected\n  actual:   $actual"
  log "SHA-256 OK: $(basename "$file")"
}

mkdir -p "$RUNTIME_ASSET_DIR" "$ROOTFS_ASSET_DIR" "$JNILIBS_DIR" "$ARKAX_ROOT/dist"
