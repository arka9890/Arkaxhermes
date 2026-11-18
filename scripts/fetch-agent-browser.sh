#!/usr/bin/env bash
# Unduh agent-browser v0.43.0 (vercel-labs) + Chrome for Testing linux-arm64.
#
# Hasil:
#   jniLibs/<abi>/libagent-browser.so   -> binary CLI yang dieksekusi dari nativeLibraryDir
#   dist/chrome-headless-shell-*.zip    -> bundel browser (TIDAK disimpan di git/workspace snapshot)
#   --stage-assets                      -> tidak berlaku lagi: Chrome TIDAK dibundel,
#                                           ZIP-nya diunduh saat runtime (ChromeDownloader)
#
# Chrome for Testing arm64 ±128 MB sengaja tidak di-commit: melewati batas snapshot
# repo. build-apk.sh memanggil --stage-assets sebelum Gradle sehingga APK akhir
# tetap membawa browser bawaan secara offline.
set -euo pipefail
source "$(dirname "$0")/common.sh"

TAG="v0.43.0"
CHROME_VERSION="157.0.8103.78"
CHROME_REVISION="1717349"
BINARY_ARM64_SHA="34be55c2b92d8d199fb9d1d62a905ee5b6ac5b1f3e8c24e5b20597f370d905e5"
BINARY_X64_SHA="8e69c9fb662514c9cf36e4911e94e913742ba066e55102486350e049dd847612"
CHROME_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux-arm64/chrome-headless-shell-linux-arm64.zip"

STAGE=0
WITH_CHROME=1
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage-assets) STAGE=1; shift ;;
    --binaries-only) WITH_CHROME=0; shift ;;
    --force) FORCE=1; shift ;;
    --tag) TAG="$2"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--stage-assets] [--binaries-only] [--force] [--tag v0.43.0]"
      exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

need curl
ABI_DIR="$JNILIBS_DIR/arm64-v8a"
mkdir -p "$ABI_DIR" "$ARKAX_ROOT/dist"

fetch_binary() {
  local abi="$1" asset="$2" sha="$3" out="$4" url
  url="https://github.com/vercel-labs/agent-browser/releases/download/${TAG}/${asset}"
  if [[ -f "$out" && $FORCE -eq 0 ]]; then
    verify_sha256 "$out" "$sha"
    return
  fi
  log "Mengunduh agent-browser ${TAG} ${abi} …"
  curl -fL --retry 3 --retry-delay 2 "$url" -o "$out.tmp"
  mv "$out.tmp" "$out"
  chmod 755 "$out"
  verify_sha256 "$out" "$sha"
}

fetch_binary "arm64-v8a" "agent-browser-linux-arm64" "$BINARY_ARM64_SHA" "$ABI_DIR/libagent-browser.so"

CHROME_ZIP="$ARKAX_ROOT/dist/chrome-headless-shell-linux-arm64.zip"
if [[ $WITH_CHROME -eq 1 ]]; then
  if [[ ! -f "$CHROME_ZIP" || $FORCE -eq 1 ]]; then
    log "Mengunduh Chrome for Testing ${CHROME_VERSION} linux-arm64 (±128 MB) …"
    curl -fL --retry 3 --retry-delay 2 "$CHROME_URL" -o "$CHROME_ZIP.tmp"
    mv "$CHROME_ZIP.tmp" "$CHROME_ZIP"
  else
    log "Chrome ZIP sudah ada di dist/: $(du -h "$CHROME_ZIP" | cut -f1)"
  fi
fi

CHROME_SHA=""
if [[ -f "$CHROME_ZIP" ]]; then
  CHROME_SHA="$(sha256_file "$CHROME_ZIP")"
fi

python3 - "$MANIFEST" "$TAG" "$CHROME_VERSION" "$CHROME_REVISION" "$CHROME_URL" "$CHROME_SHA" <<'PY'
import json, sys
path, tag, chrome_version, revision, chrome_url, chrome_sha = sys.argv[1:7]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["agentBrowser"] = {
    "repository": "https://github.com/vercel-labs/agent-browser",
    "tag": tag,
    "license": "Apache-2.0",
    "architecture": "Rust CLI + CDP daemon; live WebSocket stream + dashboard port 4848",
    "streamPort": 9223,
    "dashboardPort": 4848,
    "session": "arkaxhermes",
    "binaries": {
        "arm64-v8a": {
            "asset": "agent-browser-linux-arm64",
            "sha256": "34be55c2b92d8d199fb9d1d62a905ee5b6ac5b1f3e8c24e5b20597f370d905e5",
            "target": "android/app/src/main/jniLibs/arm64-v8a/libagent-browser.so",
        },
        "x86_64": {
            "asset": "agent-browser-linux-x64",
            "sha256": "8e69c9fb662514c9cf36e4911e94e913742ba066e55102486350e049dd847612",
            "target": "android/app/src/main/jniLibs/x86_64/libagent-browser.so",
        },
    },
}
data["chrome"] = {
    "distribution": "Chrome for Testing headless-shell",
    "version": chrome_version,
    "revision": revision,
    "platform": "linux-arm64",
    "url": chrome_url,
    "sha256": chrome_sha or None,
    "assetPack": "browser_pack",
    "asset": "chrome-headless-shell.zip",
    "note": "Diunduh scripts/fetch-agent-browser.sh ke dist/, lalu distagel ke install-time asset pack saat build APK; tidak disimpan di git agar repo ringan.",
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY

if [[ $STAGE -eq 1 ]]; then
  warn "--stage-assets tidak berlaku lagi: Chrome sengaja tidak dibundel dalam APK."
  warn "APK mengunduhnya saat Browser pertama kali dibutuhkan (ChromeDownloader), pakai URL + SHA-256 di assets/manifest.json."
fi

file "$ABI_DIR/libagent-browser.so" || true
log "agent-browser ${TAG} siap. Chrome SHA-256: ${CHROME_SHA:-belum diunduh}"
