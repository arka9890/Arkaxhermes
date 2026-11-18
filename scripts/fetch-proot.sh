#!/usr/bin/env bash
# Siapkan biner proot + dependency Termux sebagai native library Android.
#
# Android 10+ melarang execve() pada berkas di filesDir yang writable, sehingga
# proot HARUS ditaruh di jniLibs/<abi>/libproot.so dan dieksekusi dari
# applicationInfo.nativeLibraryDir. libproot.so Termux juga membutuhkan:
#   libtalloc.so.2, libandroid-shmem.so, dan libexec/proot/loader.
set -euo pipefail
source "$(dirname "$0")/common.sh"

ABI="arm64-v8a"
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --abi) ABI="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) echo "usage: $0 [--abi arm64-v8a|x86_64] [--force]"; exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

case "$ABI" in
  arm64-v8a) TERMUX_ARCH="aarch64" ;;
  x86_64)    TERMUX_ARCH="x86_64" ;;
  *) die "ABI tidak didukung: $ABI (gunakan arm64-v8a atau x86_64)" ;;
esac

OUT="$JNILIBS_DIR/$ABI"
# libtalloc.so.2 TIDAK ikut ke APK bila ditaruh di jniLibs: PackageManager hanya
# mengemas berkas bernama lib*.so, sedangkan DT_NEEDED proot meminta nama persis
# "libtalloc.so.2". Karena itu talloc dibawa sebagai asset dan diekstrak ke
# filesDir saat runtime (RuntimePaths.extractTalloc), lalu direktori itu
# ditambahkan ke LD_LIBRARY_PATH oleh ProotRuntime.
ASSET_NATIVE="$ASSET_ROOT/native/$ABI"
mkdir -p "$OUT" "$ASSET_NATIVE"
stage_talloc_asset() {
  cp -f "$1" "$ASSET_NATIVE/libtalloc.so.2"
  chmod 644 "$ASSET_NATIVE/libtalloc.so.2"
}
if [[ $FORCE -eq 0 ]]; then
  if [[ -f "$OUT/libproot.so" && -f "$ASSET_NATIVE/libtalloc.so.2" ]]; then
    log "proot + libtalloc sudah ada. Pakai --force untuk ganti."
    exit 0
  fi
  # Cache CI bisa hanya memuat jniLibs; turunkan asset talloc dari salinan itu.
  if [[ -f "$OUT/libproot.so" && -f "$OUT/libtalloc.so.2" ]]; then
    stage_talloc_asset "$OUT/libtalloc.so.2"
    log "libtalloc.so.2 disalin dari cache jniLibs ke assets"
    exit 0
  fi
fi

need curl
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

APT="https://packages.termux.dev/apt/termux-main/pool/main"

# Cari nama .deb terbaru di direktori paket Termux.
latest_deb() {
  local dir="$1" pattern="$2" index deb
  index="$(curl -fsSL "$APT/$dir/" || true)"
  deb="$(printf '%s' "$index" | grep -oE "${pattern}[^\"<>]*_${TERMUX_ARCH}\.deb" | sort -V | tail -n1 || true)"
  [[ -n "$deb" ]] || die "tidak menemukan paket $pattern di $APT/$dir/. Set PROOT_DEB_URL / build proot dari source dengan NDK."
  printf '%s\n' "$APT/$dir/$deb"
}

extract_deb() {
  local url="$1" dest="$2"
  mkdir -p "$dest"
  curl -fL --retry 3 "$url" -o "$TMP/pkg.deb"
  if command -v dpkg-deb >/dev/null 2>&1; then
    dpkg-deb -x "$TMP/pkg.deb" "$dest"
  else
    need ar
    (cd "$TMP" && rm -f data.tar.* && ar x pkg.deb)
    local data; data="$(find "$TMP" -maxdepth 1 -name 'data.tar.*' -print -quit)"
    [[ -n "$data" ]] || die "data.tar.* tidak ada di dalam .deb ($url)"
    tar -xf "$data" -C "$dest"
  fi
  rm -f "$TMP"/data.tar.* "$TMP/pkg.deb"
}

# --- 1. proot ---------------------------------------------------------------
PROOT_URL="${PROOT_DEB_URL:-$(latest_deb p/proot 'proot_')}"
log "Mengunduh $PROOT_URL"
extract_deb "$PROOT_URL" "$TMP/proot"
PROOT_BIN="$(find "$TMP/proot" -type f -path '*/bin/proot' -print -quit)"
[[ -n "$PROOT_BIN" ]] || die "biner proot tidak ditemukan di dalam paket"
cp "$PROOT_BIN" "$OUT/libproot.so"
chmod 755 "$OUT/libproot.so"
log "libproot.so → $OUT ($(du -h "$OUT/libproot.so" | cut -f1))"

# Loader yang disuntik proot ke proses yang di-trace.
LOADER="$(find "$TMP/proot" -type f -path '*/libexec/proot/loader' -print -quit)"
if [[ -n "$LOADER" ]]; then
  cp "$LOADER" "$OUT/libproot-loader.so"
  chmod 755 "$OUT/libproot-loader.so"
  log "libproot-loader.so → $OUT"
else
  warn "loader tidak ada di paket proot; ProotRuntime akan berjalan tanpanya"
fi

# --- 2. libtalloc (DT_NEEDED libtalloc.so.2) --------------------------------
TALLOC_URL="$(latest_deb libt/libtalloc 'libtalloc_')"
log "Mengunduh $TALLOC_URL"
extract_deb "$TALLOC_URL" "$TMP/talloc"
TALLOC_REAL="$(find "$TMP/talloc" -type f -name 'libtalloc.so.*' -print -quit)"
[[ -n "$TALLOC_REAL" ]] || die "libtalloc.so.* tidak ditemukan"
cp "$TALLOC_REAL" "$OUT/$(basename "$TALLOC_REAL")"
# Salinan jniLibs tidak ikut dikemas, tetapi dipakai sebagai cache untuk
# menurunkan asset saat build berikutnya.
cp "$TALLOC_REAL" "$OUT/libtalloc.so.2"
chmod 755 "$OUT/libtalloc.so.2"
stage_talloc_asset "$TALLOC_REAL"
log "libtalloc.so.2 → $OUT + $ASSET_NATIVE"

# --- 3. libandroid-shmem ----------------------------------------------------
SHMEM_URL="$(latest_deb liba/libandroid-shmem 'libandroid-shmem_')"
log "Mengunduh $SHMEM_URL"
extract_deb "$SHMEM_URL" "$TMP/shmem"
SHMEM_REAL="$(find "$TMP/shmem" -type f -name 'libandroid-shmem.so*' -print -quit)"
[[ -n "$SHMEM_REAL" ]] || die "libandroid-shmem.so tidak ditemukan"
cp "$SHMEM_REAL" "$OUT/$(basename "$SHMEM_REAL")"
chmod 755 "$OUT/$(basename "$SHMEM_REAL")"
log "$(basename "$SHMEM_REAL") → $OUT"

file "$OUT/libproot.so" || true
cat > "$OUT/README.txt" <<'TXT'
Berkas ini dihasilkan scripts/fetch-proot.sh dari paket Termux:
  libproot.so            biner proot (dieksekusi dari nativeLibraryDir)
  libproot-loader.so     PROOT_LOADER untuk proses yang di-trace
  libtalloc.so.2         DT_NEEDED dari libproot.so
  libtalloc.so.2.5.0     berkas asli paket
  libandroid-shmem.so    DT_NEEDED dari libproot.so
LD_LIBRARY_PATH dan PROOT_LOADER diisi oleh ProotRuntime.kt.
Sumber: termux/proot, libtalloc, libandroid-shmem (GPL/LGPL, lihat copyright paket).
TXT
log "Selesai: $(ls -1 "$OUT" | tr '\n' ' ')"
