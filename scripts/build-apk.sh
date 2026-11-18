#!/usr/bin/env bash
# Rakit APK Arkaxhermes. Jalankan scripts/make-assets.sh lebih dulu.
set -euo pipefail
source "$(dirname "$0")/common.sh"

VARIANT="debug"
while [[ $# -gt 0 ]]; do
  case "$1" in
    debug|release) VARIANT="$1"; shift ;;
    -h|--help) echo "usage: $0 [debug|release]"; exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

[[ -f "$ASSET_ROOT/www/index.html" ]] || die "UI belum ada: $ASSET_ROOT/www/index.html"
[[ -d "$ANDROID_DIR" ]] || die "direktori proyek Android hilang"

# Pastikan binary agent-browser + Chrome for Testing tersedia dan distagel ke asset pack.
"$ARKAX_ROOT/scripts/fetch-agent-browser.sh" --stage-assets >/dev/null || die "aset browser bawaan belum siap"
if [[ ! -f "$ROOTFS_ASSET_DIR/rootfs.sha256" ]]; then
  warn "rootfs belum dibundel — APK akan tetap terbuild tetapi first-run membutuhkan jaringan / asset belum lengkap."
  warn "Jalankan: ./scripts/make-assets.sh"
fi

if [[ -z "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" && ! -f "$ANDROID_DIR/local.properties" ]]; then
  die "set ANDROID_HOME atau buat android/local.properties berisi sdk.dir=…"
fi

GRADLEW="$ANDROID_DIR/gradlew"
WRAPPER_JAR="$ANDROID_DIR/gradle/wrapper/gradle-wrapper.jar"
# gradle-wrapper.jar ada di .gitignore dan gradlew yang ter-commit hanya stub,
# jadi yang diperiksa bukan hanya bit executable-nya.
if [[ ! -x "$GRADLEW" || ! -f "$WRAPPER_JAR" ]]; then
  if command -v gradle >/dev/null 2>&1; then
    log "wrapper Gradle belum lengkap (gradlew/gradle-wrapper.jar), membuat ulang …"
    (cd "$ANDROID_DIR" && gradle wrapper --gradle-version 8.9)
    chmod +x "$GRADLEW"
  else
    die "wrapper Gradle tidak lengkap dan 'gradle' tidak di PATH. Pasang Gradle 8.9 atau buka proyek dengan Android Studio sekali untuk menghasilkannya."
  fi
fi

case "$VARIANT" in
  debug)   TASK="assembleDebug" ;;
  release) TASK="assembleRelease" ;;
esac

log "Menjalankan :app:$TASK …"
(cd "$ANDROID_DIR" && ./gradlew ":app:$TASK" --stacktrace)

VERSION="$(grep -oE 'versionName "[^"]+"' "$ANDROID_DIR/app/build.gradle.kts" | head -n1 | cut -d'"' -f2 || echo 0.1.0)"
SRC="$(find "$ANDROID_DIR/app/build/outputs/apk/$VARIANT" -name '*.apk' -print -quit 2>/dev/null || true)"
if [[ -n "$SRC" ]]; then
  DEST="$ARKAX_ROOT/dist/Arkaxhermes-$VARIANT-$VERSION.apk"
  cp "$SRC" "$DEST"
  log "APK siap: $DEST ($(du -h "$DEST" | cut -f1))"
  log "Install:  adb install -r $DEST"
else
  warn "Build selesai tetapi APK tidak ditemukan di direktori output."
fi
