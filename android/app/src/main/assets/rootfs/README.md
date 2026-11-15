# Aset rootfs (dibuat saat build, tidak disimpan di git)

`scripts/build-rootfs.sh` menaruh di sini:

- `ubuntu-rootfs.tar.gz.part001`, `.part002`, … — arsip Ubuntu Base 24.04.5 + `/opt/arkax`, dipecah 24 MB.
- `rootfs.sha256` — SHA-256 arsip gabungan (wajib, diverifikasi `RootfsInstaller.kt`).
- `README.txt` — catatan yang dibuat skrip.

`RootfsInstaller.kt` menggabungkan bagian-bagian itu di `filesDir`, memverifikasi checksum, lalu mengekstrak dengan parser TAR internal. Bila folder ini kosong, APK tetap terbuild tetapi first-run akan gagal dengan pesan yang jelas — jalankan `./scripts/make-assets.sh` dulu.

Lihat [docs/PROOTFS.md](../../../../../docs/PROOTFS.md) dan [docs/BUILD.md](../../../../../docs/BUILD.md).
