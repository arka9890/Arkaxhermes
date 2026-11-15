#!/usr/bin/env bash
# Satu perintah untuk menyiapkan SELURUH aset biner APK.
set -euo pipefail
source "$(dirname "$0")/common.sh"

ARCH="arm64"
ABI="arm64-v8a"
TAG="$(manifest_get hermesSrc.tag)"
SKIP_ROOTFS=0
FULL_HERMES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --abi) ABI="$2"; shift 2 ;;
    --hermes-tag) TAG="$2"; shift 2 ;;
    --skip-rootfs) SKIP_ROOTFS=1; shift ;;
    --full-hermes) FULL_HERMES=1; shift ;;
    -h|--help)
      echo "usage: $0 [--arch arm64|amd64] [--abi arm64-v8a|x86_64] [--hermes-tag v0.23.1] [--skip-rootfs] [--full-hermes]"
      echo "  default: source Hermes dibundel dalam pack --slim; --full-hermes memakai arsip upstream utuh"
      exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

if [[ "$ARCH" == "arm64" && "$ABI" != "arm64-v8a" ]]; then
  warn "--arch arm64 biasanya dipasangkan dengan --abi arm64-v8a (diminta: $ABI)"
fi
if [[ "$ARCH" == "amd64" && "$ABI" != "x86_64" ]]; then
  warn "--arch amd64 biasanya dipasangkan dengan --abi x86_64 (diminta: $ABI)"
fi

log "=== 1/4  proot ($ABI) ==="
"$ARKAX_ROOT/scripts/fetch-proot.sh" --abi "$ABI" --force

log "=== 2/4  source Hermes Agent ($TAG) ==="
if [[ $FULL_HERMES -eq 1 ]]; then
  "$ARKAX_ROOT/scripts/fetch-hermes-src.sh" --tag "$TAG" --force
else
  "$ARKAX_ROOT/scripts/fetch-hermes-src.sh" --tag "$TAG" --slim --force
fi

if [[ $SKIP_ROOTFS -eq 0 ]]; then
  log "=== 3/4  rootfs Ubuntu ($ARCH) ==="
  "$ARKAX_ROOT/scripts/build-rootfs.sh" --arch "$ARCH"
else
  warn "rootfs dilewati (--skip-rootfs)"
fi

log "=== 4/4  ringkasan ==="
printf '\n'
printf '  %-52s %s\n' "jniLibs/$ABI/libproot.so" \
  "$( [[ -f "$JNILIBS_DIR/$ABI/libproot.so" ]] && du -h "$JNILIBS_DIR/$ABI/libproot.so" | cut -f1 || echo 'BELUM ADA' )"
printf '  %-52s %s\n' "assets/runtime/hermes-src.tar.gz" \
  "$( [[ -f "$RUNTIME_ASSET_DIR/hermes-src.tar.gz" ]] && du -h "$RUNTIME_ASSET_DIR/hermes-src.tar.gz" | cut -f1 || echo 'BELUM ADA' )"
printf '  %-52s %s\n' "assets/rootfs/ubuntu-rootfs.tar.gz.part*" \
  "$( ls "$ROOTFS_ASSET_DIR"/ubuntu-rootfs.tar.gz.part* 2>/dev/null | wc -l ) bagian"
printf '  %-52s %s\n' "assets/www/index.html" \
  "$( [[ -f "$ASSET_ROOT/www/index.html" ]] && echo OK || echo 'HILANG' )"
printf '\n'
log "Lanjutkan dengan: ./scripts/build-apk.sh debug"
