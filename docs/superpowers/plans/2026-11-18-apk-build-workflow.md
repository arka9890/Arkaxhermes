# Workflow Build APK di GitHub Actions — Rencana Implementasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Actions merakit APK debug arm64 setiap push ke `main` dan lewat tombol manual, dengan identitas tanda tangan permanen sehingga APK baru bisa menimpa versi terpasang tanpa uninstall.

**Architecture:** Satu keystore Arkaxhermes dipakai bersama oleh CI (lewat secret) dan build lokal (lewat `android/local.properties`), dan `buildType.debug` diarahkan memakainya. Alur CI memakai skrip yang sudah ada (`make-assets.sh`, `build-apk.sh`) apa adanya, ditambah cache aset biner karena seluruh aset di-`.gitignore` dan harus diunduh (±250 MB) setiap build.

**Tech Stack:** GitHub Actions (`ubuntu-24.04`), JDK 17 Temurin, Gradle 8.9 + AGP 8.7.3, `actions/cache`, `keytool`, GitHub REST API untuk memasang secret.

**Spec:** `docs/superpowers/plans/2026-11-18-apk-build-workflow.md` (dokumen ini adalah spec + rencana; keputusan desain disetujui di percakapan: debug artifact saja, keystore baru, uninstall sekali).

## Global Constraints

- APK yang dihasilkan: `app-arm64-v8a-debug.apk` (dari `splits.abi`, `isUniversalApk = false`), bukan APK x86_64.
- `applicationId` tetap `com.arkaxhermes.app.debug` (`applicationIdSuffix = ".debug"` tidak diubah).
- `versionName` tetap `0.1.0`. `versionCode` = jumlah commit git, cadangan `1`.
- Aset biner tidak pernah di-commit (semua sudah ada di `.gitignore`); `rootfs/manifest.json` yang ditulis ulang oleh skrip unduh **tidak** di-commit.
- Nama secret: `ARKAX_KEYSTORE_B64`, `ARKAX_STORE_PASSWORD`, `ARKAX_KEY_ALIAS`, `ARKAX_KEY_PASSWORD`.
- Pesan commit dan komentar kode berbahasa Indonesia, mengikuti gaya repo.

## Review Focus

- APK baru ditolak saat instalasi karena kunci berbeda (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`) — perilaku yang diharapkan: satu kali uninstall, setelah itu semua build saling menimpa.
- `versionCode` APK CI lebih rendah dari yang terpasang (`INSTALL_FAILED_VERSION_DOWNGRADE`) — dijamin oleh hitungan commit yang monoton.
- (Sudah teratasi) Chrome tidak lagi memakai asset pack; APK mengunduh ZIP saat runtime.
- Build CI kehabisan waktu atau kuota karena mengunduh ulang ±250 MB — dijamin oleh `actions/cache`.
- Keystore tidak terbaca di CI karena path di `local.properties` relatif terhadap modul `android/app` — gunakan path absolut.

---

### Task 1: Identitas tanda tangan permanen

**Files:**
- Modify: `android/app/build.gradle.kts:12-48`
- Create (lokal, tidak di-commit): `arkax-release.jks`

**Interfaces:**
- Produces: `signingConfigs["arkaxRelease"]` aktif bila `local.properties` memuat `ARKAX_STORE_FILE`; `buildTypes.debug.signingConfig` menunjuk ke sana bila ada; `android.defaultConfig.versionCode` = jumlah commit git atau `1`.

- [ ] **Step 1: Buat keystore** dengan `keytool -genkeypair -alias arkax -keyalg RSA -keysize 4096 -validity 10950`, password acak yang disimpan.
- [ ] **Step 2: Pasang 4 secret** ke repo `arka9890/Arkaxhermes` lewat REST API (nilai dienkripsi sealed box dengan public key repo).
- [ ] **Step 3: Verifikasi** `GET /actions/secrets` mengembalikan 4 nama tersebut.
- [ ] **Step 4: Ubah `build.gradle.kts`** — `versionCode` dari git, dan `debug` memakai `arkaxRelease` bila tersedia.
- [ ] **Step 5: Verifikasi** berkas tetap seimbang kurungnya dan lolos `check.sh`.

### Task 2: Penjaga wrapper Gradle di `build-apk.sh`

**Files:**
- Modify: `scripts/build-apk.sh:34-43`

**Interfaces:**
- Consumes: tidak ada.
- Produces: `build-apk.sh` membuat wrapper bila `gradle-wrapper.jar` tidak ada, bukan hanya bila `gradlew` tidak executable.

- [ ] **Step 1: Ubah kondisi** menjadi memeriksa `-x "$GRADLEW"` **atau** `gradle-wrapper.jar` tidak ada.
- [ ] **Step 2: Verifikasi** `bash -n scripts/build-apk.sh` lolos dan `check.sh` tetap hijau.

### Task 3: Workflow APK

**Files:**
- Create: `.github/workflows/apk.yml`

**Interfaces:**
- Consumes: `scripts/check.sh`, `scripts/make-assets.sh`, `scripts/build-apk.sh debug`, keempat secret dari Task 1.
- Produces: artifact `Arkaxhermes-debug-arm64` berisi `*.apk`.

- [ ] **Step 1: Tulis workflow** — pemicu `push` ke `main` + `workflow_dispatch`; langkah: checkout `fetch-depth: 0`, JDK 17 Temurin, `keytool` tidak perlu, tulis `android/local.properties` dari secret, cache aset dengan kunci hash `rootfs/manifest.json`, `./scripts/check.sh`, `./scripts/make-assets.sh`, `./scripts/build-apk.sh debug`, unggah `android/app/build/outputs/apk/debug/app-arm64-v8a-debug.apk`.
- [ ] **Step 2: Verifikasi** YAML valid (parse dengan Python `yaml` bila tersedia; jika tidak, `python3 -c` dengan `json`-style check tidak berlaku — gunakan `ruby`/`yq` atau minimal cek indentasi manual).
- [ ] **Step 3: Commit + push**, lalu pantau run sampai `completed`.
- [ ] **Step 4: Bila run merah**, baca log job lewat REST API, perbaiki akar masalahnya, ulangi. Bila merah karena asset pack tidak didukung APK, pindah ke jalur cadangan: salin ZIP ke `android/app/src/main/assets/browser/` dan lepas `assetPacks += ":browser_pack"` untuk build APK.

### Task 4: Dokumentasi

**Files:**
- Modify: `docs/BUILD.md` (bagian 6 Build APK + bagian 7 keystore)
- Modify: `README.md` (bagian status/CI)

**Interfaces:**
- Consumes: nama secret dan path keystore dari Task 1.

- [ ] **Step 1: Tulis** cara mengunduh APK dari Actions, dan cara memasang keystore yang sama untuk build lokal (`android/local.properties` dengan path absolut atau relatif terhadap `android/app`, plus 4 kunci `ARKAX_*`).
- [ ] **Step 2: Verifikasi** `./scripts/check.sh` tetap hijau (README wajib menyebut `Arkaxhermes` dan `v0.23.1`).
- [ ] **Step 3: Commit + push.**

### Task 5: Serah terima

- [ ] **Step 1: Konfirmasi run hijau** dan artifact tersedia; laporkan tautan unduhan.
- [ ] **Step 2: Sampaikan** bahwa uninstall sekali diperlukan karena kunci berubah, lalu instal APK dari artifact.