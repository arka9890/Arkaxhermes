#!/usr/bin/env bash
# Bangun rootfs Ubuntu 24.04 berisi runtime Arkaxhermes + source Hermes.
# Menghasilkan ubuntu-rootfs.tar.gz.partNNN + rootfs.sha256 untuk aset APK.
set -euo pipefail
source "$(dirname "$0")/common.sh"

ARCH="arm64"
RELEASE="$(manifest_get ubuntu.release)"
WITH_APT=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --release) RELEASE="$2"; shift 2 ;;
    --no-apt) WITH_APT=0; shift ;;
    -h|--help) echo "usage: $0 [--arch arm64|amd64] [--release 24.04.5] [--no-apt]"; exit 0 ;;
    *) die "argumen tidak dikenal: $1" ;;
  esac
done

case "$ARCH" in
  arm64|amd64) ;;
  *) die "arsitektur tidak didukung: $ARCH" ;;
esac

need curl
need tar
need python3
need sha256sum
need split

FILE="ubuntu-base-${RELEASE}-base-${ARCH}.tar.gz"
EXPECT="$(python3 - "$MANIFEST" "$ARCH" "$RELEASE" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
arch, release = sys.argv[2], sys.argv[3]
expected_file = f"ubuntu-base-{release}-base-{arch}.tar.gz"
node = m["ubuntu"]["architectures"][arch]
assert node["file"] == expected_file, f"manifest masih memin {node['file']}, diminta {expected_file}"
print(node["sha256"])
PY
)"
URL="$(manifest_get ubuntu.baseUrl)/$FILE"

WORK="$ARKAX_ROOT/rootfs/work/$ARCH-$RELEASE"
CACHE="$ARKAX_ROOT/rootfs/work/cache"
mkdir -p "$WORK" "$CACHE"

if [[ ! -f "$CACHE/$FILE" ]]; then
  log "Mengunduh $URL …"
  curl -fL --retry 3 --retry-delay 2 "$URL" -o "$CACHE/$FILE.tmp"
  mv "$CACHE/$FILE.tmp" "$CACHE/$FILE"
fi
verify_sha256 "$CACHE/$FILE" "$EXPECT"

log "Mengekstrak base Ubuntu ke $WORK …"
rm -rf "$WORK/root"
mkdir -p "$WORK/root"
tar -xzf "$CACHE/$FILE" -C "$WORK/root" --numeric-owner

# --- Konfigurasi dasar di dalam rootfs -------------------------------------
mkdir -p "$WORK/root/etc/apt/sources.list.d" "$WORK/root/opt/arkax" \
         "$WORK/root/mnt/arkax/inbox" "$WORK/root/mnt/arkax/exports" \
         "$WORK/root/mnt/arkax/scripts" "$WORK/root/root/.hermes"

cat > "$WORK/root/etc/resolv.conf" <<'DNS'
nameserver 1.1.1.1
nameserver 8.8.8.8
options timeout:5 attempts:2 rotate
DNS

MIRROR="http://ports.ubuntu.com/ubuntu-ports"
[[ "$ARCH" == "amd64" ]] && MIRROR="http://archive.ubuntu.com/ubuntu"
cat > "$WORK/root/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: $MIRROR
Suites: noble noble-updates noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

cat > "$WORK/root/etc/hostname" <<'EOF'
arkaxhermes
EOF
printf '127.0.0.1 localhost arkaxhermes\n' > "$WORK/root/etc/hosts"
printf 'ARKAX_ROOTFS=ubuntu-%s-%s\n' "$RELEASE" "$ARCH" > "$WORK/root/etc/arkax-release"
printf 'LANG=C.UTF-8\nLC_ALL=C.UTF-8\n' > "$WORK/root/etc/default/locale"

# --- Skrip runtime + source Hermes -----------------------------------------
# Salin skrip runtime, TAPI jangan salin source Hermes: berkas itu sudah
# dibundel sekali sebagai aset dan akan terlihat di /opt/arkax lewat bind
# mount filesDir/runtime → /opt/arkax (ProotRuntime). Menyalin di sini hanya
# menggandakan puluhan MB ke dalam arsip rootfs.
for entry in "$RUNTIME_ASSET_DIR"/*; do
  [[ "$(basename "$entry")" == "hermes-src.tar.gz" ]] && continue
  cp -a "$entry" "$WORK/root/opt/arkax/"
done
chmod 755 "$WORK/root/opt/arkax/"*.sh
# Source Hermes TIDAK diduplikasi ke dalam rootfs: filesDir/arkax/runtime
# di-bind ProotRuntime ke /opt/arkax, jadi /opt/arkax/hermes-src.tar.gz sudah
# tersedia di dalam proot. Menyalin juga ke sini hanya menggandakan puluhan MB.
if [[ -f "$RUNTIME_ASSET_DIR/hermes-src.tar.gz" ]]; then
  log "Source Hermes tersedia sebagai aset terpisah ($(du -h "$RUNTIME_ASSET_DIR/hermes-src.tar.gz" | cut -f1)) → /opt/arkax via bind mount"
else
  warn "hermes-src.tar.gz belum ada — jalankan scripts/fetch-hermes-src.sh. First-run akan clone dari GitHub."
fi

# --- Pasang paket APT tanpa root memakai proot di host (opsional) -----------
PACKAGES="$(manifest_get runtime.defaultPackages | python3 -c 'import json,sys; print(" ".join(json.load(sys.stdin)))')"
if [[ $WITH_APT -eq 1 ]]; then
  PROOT_BIN="${PROOT_BIN:-$(command -v proot || true)}"
  if [[ -n "$PROOT_BIN" && -x "$PROOT_BIN" ]]; then
    log "Menjalankan apt di dalam proot host (tanpa root) …"
    "$PROOT_BIN" -0 -r "$WORK/root" -w / -b /proc -b /dev -b /sys --link2symlink \
      /usr/bin/env -i HOME=/root DEBIAN_FRONTEND=noninteractive \
      PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LANG=C.UTF-8 \
      /bin/bash -lc "apt-get update -qq && apt-get install -y --no-install-recommends $PACKAGES && apt-get clean && rm -rf /var/lib/apt/lists/*" \
      || warn "apt di host gagal (aman): dependency akan dipasang saat first run oleh bootstrap.sh"
  else
    warn "proot tidak ada di host; dependency dipasang saat first run di perangkat (--no-apt untuk diam)."
  fi
fi

# --- Arsip + pecah menjadi bagian kecil ------------------------------------
log "Membuat arsip terkompresi …"
FULL="$WORK/ubuntu-rootfs.tar.gz"
tar -czf "$FULL" -C "$WORK/root" --numeric-owner .
FULL_SHA="$(sha256_file "$FULL")"

rm -f "$ROOTFS_ASSET_DIR"/ubuntu-rootfs.tar.gz.part* "$ROOTFS_ASSET_DIR"/ubuntu-rootfs.tar.gz
PART_MB="$(manifest_get runtime.partSizeMb)"
split -b "${PART_MB}M" -d -a 3 --numeric-suffixes=1 "$FULL" "$ROOTFS_ASSET_DIR/ubuntu-rootfs.tar.gz.part"
printf '%s\n' "$FULL_SHA" > "$ROOTFS_ASSET_DIR/rootfs.sha256"

cat > "$ROOTFS_ASSET_DIR/README.txt" <<'TXT'
Ubuntu Base 24.04 + /opt/arkax Arkaxhermes runtime. Arsip dipecah 24 MB per bagian;
RootfsInstaller.kt menggabungkan sesuai urutan nama, memverifikasi SHA-256 terhadap
rootfs.sha256, lalu mengekstrak dengan parser TAR internal (tanpa biner tar Android).
Jangan menghapus rootfs.sha256 — tidak ada opsi melewati verifikasi di UI.
TXT

log "Selesai: $(ls "$ROOTFS_ASSET_DIR"/ubuntu-rootfs.tar.gz.part* | wc -l) bagian, total $(du -ch "$ROOTFS_ASSET_DIR"/ubuntu-rootfs.tar.gz.part* | tail -n1 | cut -f1)"
log "SHA-256 gabungan: $FULL_SHA"
