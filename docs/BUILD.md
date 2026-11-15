# Build Arkaxhermes dari source

## 0. Ringkasan alur

```
scripts/fetch-proot.sh      → android/app/src/main/jniLibs/<abi>/libproot.so
scripts/fetch-hermes-src.sh → android/app/src/main/assets/runtime/hermes-src.tar.gz
scripts/build-rootfs.sh     → android/app/src/main/assets/rootfs/ubuntu-rootfs.tar.gz.partNNN
scripts/build-apk.sh        → android/app/build/outputs/apk/{debug,release}/app-*.apk
```

`make-assets.sh` menjalankan tiga yang pertama sekaligus. **Di repo Arkaxhermes yang dikirimkan, ketiga hasil itu sudah ada** (≈80 MB, sengaja ikut ter-commit agar built-in distro benar-benar ada): `libproot.so` + loader + dependency, `ubuntu-rootfs.tar.gz.part001/002` + `rootfs.sha256`, dan `hermes-src.tar.gz` pack slim. Jalankan skrip hanya bila ingin membangun ulang, mengganti tag, atau menambah ABI x86_64. Artefak perantara (`rootfs/work/`, arsip utuh, `dist/`) tetap di-`.gitignore`.

---

## 1. Prasyarat

| Kebutuhan | Versi minimum | Catatan |
| --- | --- | --- |
| Host build | Linux x86_64 (Ubuntu 22.04+ disarankan), WSL2 juga bisa | `curl`, `tar`, `xz`, `sha256sum`, `git`, `python3` |
| Android Studio / SDK | SDK Platform 35, Build Tools 35.x | `ANDROID_HOME` atau `local.properties` |
| Android NDK | 26.x+ | hanya untuk build `proot` dari source (opsi B) |
| JDK | 17 | AGP 8.x |
| Gradle | 8.9+ | Android Studio menyediakan wrapper; jalankan `gradle wrapper` sekali bila `gradlew` belum ada |
| Perangkat | Android 8.0 (API 26)+, **arm64-v8a** direkomendasikan | x86_64 didukung untuk emulator dengan rootfs amd64 |
| Ruang disk | ≥ 6 GB | rootfs + dependency Python/Node + Gradle cache |
| Jaringan | ya, saat build | saat runtime bisa offline bila aset dibundel + model lokal/Ollama |

Perangkat 32-bit (`armeabi-v7a`) tidak didukung: Hermes upstream hanya menyediakan paket Android untuk aarch64 dan Python 3.14 tidak tersedia untuk ABI itu.

---

## 2. Siapkan `proot`

### Opsi A — biner Termux (tercepat)

```bash
./scripts/fetch-proot.sh --abi arm64-v8a
```

Skrip mengunduh **tiga** paket Termux: `proot`, `libtalloc`, dan `libandroid-shmem`. Hasilnya di `jniLibs/arm64-v8a/`:

```
libproot.so            biner proot (DT_NEEDED: libtalloc.so.2, libandroid-shmem.so, libc.so)
libproot-loader.so     dari usr/libexec/proot/loader → PROOT_LOADER
libtalloc.so.2         salinan dengan nama persis sesuai DT_NEEDED
libtalloc.so.2.5.0     berkas asli paket
libandroid-shmem.so    shm emulation Android
```

Penamaan `.so` **wajib**: sejak Android 10 (API 29) biner yang dapat dieksekusi hanya boleh berada di direktori native library aplikasi (`nativeLibraryDir`), bukan di `filesDir`. `ProotRuntime.kt` mengisi `LD_LIBRARY_PATH=<nativeLibraryDir>` dan `PROOT_LOADER=<nativeLibraryDir>/libproot-loader.so` pada **proses proot** (bukan pada `env -i` di dalam rootfs).

Jika URL paket berubah, berikan langsung:

```bash
PROOT_DEB_URL=https://packages.termux.dev/apt/termux-main/pool/main/p/proot/proot_5.1.107-1_aarch64.deb \
  ./scripts/fetch-proot.sh --abi arm64-v8a
```

### Opsi B — build dari source dengan NDK

```bash
git clone --depth 1 https://github.com/termux/proot.git /tmp/proot
cd /tmp/proot/src
# ikuti README upstream: libtalloc + build static, lalu
cp proot $ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android26-clang \
  # (gunakan toolchain NDK untuk target aarch64)
cp proot ../../Arkaxhermes/android/app/src/main/jniLibs/arm64-v8a/libproot.so
```

Verifikasi di host:

```bash
file android/app/src/main/jniLibs/arm64-v8a/libproot.so   # ELF aarch64 / statically linked
```

`ProotRuntime.kt` menemukan biner lewat `applicationInfo.nativeLibraryDir` dan secara otomatis mengisi `PROOT_LOADER` bila berkas loader ada. Manifest memakai `android:extractNativeLibs="true"` dan `jniLibs.useLegacyPackaging = true` agar berkas benar-benar ada di disk.

---

## 3. Pin source Hermes Agent

```bash
./scripts/fetch-hermes-src.sh --tag v0.23.1 --slim
```

Mengunduh tarball rilis dari `github.com/NousResearch/hermes-agent`, menghitung SHA-256, dan menulis nilainya ke `rootfs/manifest.json`. Source ini dibundel agar **instalasi pertama tidak membutuhkan internet**.

`--slim` membuang `tests/`, `website/`, `contributors/`, `.github/`, `evals/`, `tests-js/`, `nix/` (88 MB → 51 MB) **tanpa** menyentuh `apps/`, `agent/`, `tools/`, `gateway/`, `hermes_cli/`, `skills/`, `plugins/`, `optional-skills/`, sehingga dashboard/Desktop/TUI source tetap ada. Tanpa `--slim` Anda mendapat arsip upstream utuh. Repo ini sudah memuat hasil `--slim` dari `v0.23.1` (SHA-256 ada di manifest). Untuk versi terbaru:

```bash
./scripts/fetch-hermes-src.sh --tag main --slim --force
```

Perbarui Hermes di perangkat lewat Pengaturan → "Perbarui Hermes" (`hermes update`) atau ulangi langkah ini lalu build ulang APK.

---

## 4. Bangun rootfs Ubuntu 24.04

```bash
./scripts/build-rootfs.sh --arch arm64 --release 24.04.5
```

Yang terjadi:

1. Unduh `ubuntu-base-24.04.5-base-arm64.tar.gz` dari `cdimage.ubuntu.com`, cocokkan SHA-256 dengan `rootfs/manifest.json` (nilai nyata dari berkas `SHA256SUMS` upstream).
2. Ekstrak ke direktori kerja, tulis `/etc/resolv.conf`, `/etc/apt/sources.list.d/ubuntu.sources`, locale `C.UTF-8`.
3. Salin `assets/runtime/*` ke `/opt/arkax/` dan source Hermes ke `/opt/arkax/hermes-src.tar.gz`.
4. Bila `proot` tersedia di host, jalankan `proot -0 -r <rootfs> apt-get update && apt-get install …` tanpa root (python3, python3-venv, python3-pip, git, curl, ca-certificates, nodejs, npm, ripgrep, ffmpeg, tzdata). Bila tidak ada, langkah ini dilewati dan dilakukan saat first run di perangkat (`bootstrap.sh`).
5. `tar -czf` → pecah menjadi bagian 24 MB (`ubuntu-rootfs.tar.gz.part001`, …) agar aapt/APK tidak bermasalah dengan aset besar. `RootfsInstaller` menggabungkan kembali dengan urutan nama berkas dan memverifikasi checksum gabungan.

`aaptOptions.noCompress` di `app/build.gradle.kts` already mencakup `gz`, `tgz`, `part`, `tar`, `xz`, `zip`, `so`, `bin` supaya arsip ter-`gzip` tidak dikompresi ulang.

**Ukuran nyata di repo ini**: base Ubuntu 28 MB (2 bagian: 24 MB + 3,9 MB). Karena host build sandbox tidak punya proot aarch64 yang bisa dijalankan, paket APT belum dipasang ke dalam rootfs; `bootstrap.sh` melakukannya saat first run di perangkat (butuh jaringan sekali). Bila Anda build di Linux dengan `proot` terpasang, skrip memasang Python/Node/git/ffmpeg/ripgrep lebih dulu → rootfs jadi ≈350–600 MB terkompresi dan first-run benar-benar offline. Source Hermes (51 MB) **tidak** diduplikasi ke dalam rootfs: `filesDir/runtime` di-bind ke `/opt/arkax`, jadi `install-hermes.sh` tetap menemukannya. Gunakan APK split per ABI atau Play Asset Delivery untuk distribusi resmi (batas 150 MB per APK base; lihat [docs/PROOTFS.md](docs/PROOTFS.md#distribusi)).

---

## 5. Rakit semua aset

Aset di repo sudah dirakit, jadi langkah ini **opsional**. Untuk membangun ulang (misal ganti tag atau ABI emulator):

```bash
./scripts/make-assets.sh --arch arm64 --hermes-tag v0.23.1 --abi arm64-v8a
# --full-hermes bila ingin arsip upstream utuh 88 MB, bukan pack slim 51 MB
```

Hasil akhir:

```
android/app/src/main/assets/rootfs/ubuntu-rootfs.tar.gz.part001 …
android/app/src/main/assets/rootfs/rootfs.sha256
android/app/src/main/assets/runtime/hermes-src.tar.gz
android/app/src/main/jniLibs/arm64-v8a/libproot.so
```

`rootfs.sha256` dibaca `RootfsInstaller` untuk verifikasi; bila tidak cocok, instalasi dihentikan (tidak ada opsi "lewati verifikasi" di UI).

---

## 6. Build APK

```bash
# pertama kali, bila gradle wrapper belum ada:
cd android && gradle wrapper --gradle-version 8.9 && cd ..
chmod +x android/gradlew

./scripts/build-apk.sh debug
# atau
./scripts/build-apk.sh release   # butuh keystore, lihat bagian 7
```

`build-apk.sh` memanggil `./gradlew :app:assembleDebug`, lalu menyalin APK ke `dist/Arkaxhermes-<variant>-<version>.apk`.

```bash
adb install -r dist/Arkaxhermes-debug-0.1.0.apk
adb logcat -s Arkaxhermes ArkaxHttpServer ProotRuntime HermesRuntime
```

---

## 7. Rilis & signing

```bash
keytool -genkeypair -v -keystore arkaxhermes.jks -alias arkaxhermes \
  -keyalg RSA -keysize 2048 -validity 10000
```

Isi `android/local.properties` (jangan di-commit):

```
sdk.dir=/home/you/Android/Sdk
ARKAX_STORE_FILE=/abs/path/arkaxhermes.jks
ARKAX_STORE_PASSWORD=***
ARKAX_KEY_ALIAS=arkaxhermes
ARKAX_KEY_PASSWORD=***
```

`app/build.gradle.kts` membaca properti itu untuk `signingConfigs.release`; bila tidak ada, build release jatuh ke debug signing dengan peringatan.

---

## 8. Validasi tanpa Android SDK

```bash
./scripts/check.sh
```

Memeriksa: `bash -n` semua skrip, `python3 -m py_compile` bridge, `node --check` JS yang diekstrak dari `index.html`, kevalidan JSON, keberadaan file wajib, dan daftar TODO. CI menjalankan ini otomatis (`.github/workflows/ci.yml`).

---

## 9. Troubleshooting

| Gejala | Penyebab | Perbaikan |
| --- | --- | --- |
| `permission denied` saat menjalankan proot | biner ditaruh di `filesDir` | pastikan di `jniLibs/<abi>/libproot.so` + `extractNativeLibs=true` |
| `ERROR: not a dynamic executable` / loader hilang | Termux proot butuh `libproot-loader.so` | jalankan `fetch-proot.sh` lagi; cek env `PROOT_LOADER` di `ProotRuntime` |
| `chown`/`apt` gagal di dalam proot | proot memalsukan root tapi filesystem Android (F2FS/sdcardfs) tidak mendukung ownership | `--link2symlink`, hindari hardlink; rootfs harus di `filesDir`, **bukan** `/sdcard` |
| UI kosong / `net::ERR_CONNECTION_REFUSED` | server jembatan belum start atau port bentrok | `ArkaxHttpServer` mencoba 18789→18799; cek logcat |
| Ekstraksi rootfs lambat / gagal | memori atau ruang kurang | butuh ≈ 2× ukuran arsip ruang kosong; UI menampilkan progres per berkas |
| `hermes: command not found` | `install-hermes.sh` gagal | buka Terminal → `bash /opt/arkax/install-hermes.sh --verbose` |
| Gateway mati saat layar padam | Android membunuh proses background | aktifkan pengecualian optimasi baterai; `AgentService` + wake lock |
| Model tidak merespons | DNS di rootfs | `bootstrap.sh` menulis `/etc/resolv.conf`; cek `/api/exec` → `getent hosts api.openai.com` |
| Shear: `hermes --tui` tidak interaktif | tidak ada PTY asli | layar Terminal memakai `script -q -c` di dalam rootfs; lihat [docs/PROOTFS.md](docs/PROOTFS.md#tty) |
