# Arkaxhermes ☤

**Hermes Agent (Nous Research) di Android, berjalan di dalam distro Ubuntu proot yang dibundel langsung di APK.**

Arkaxhermes membungkus [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT) menjadi satu aplikasi Android. Bukan sekadar "remote client": rootfs Ubuntu 24.04, source Hermes yang dipin, `proot`, dan skrip instalasi ikut terpasang di dalam aplikasi. Pertama kali dibuka, aplikasi mengekstrak rootfs ke direktori privatnya, menyelesaikan instalasi Python/Node/Hermes, lalu menyalakan server jembatan lokal (`127.0.0.1`) yang dipakai UI untuk berbicara dengan `hermes` CLI, TUI, gateway, cron, skills, memory, MCP, dan seluruh fitur lainnya.

Nama repo / aplikasi: **Arkaxhermes** · Package: `com.arkaxhermes.app` · Versi: `0.1.0`

---

## Yang ada di repo ini

| Bagian | Isi |
| --- | --- |
| `android/app/src/main/java/...` | Aplikasi Android native (Kotlin, WebView, foreground service, Android Keystore) |
| `android/app/src/main/assets/www/index.html` | UI lengkap: Chat, Provider, Workspace, Terminal, Pengaturan + 20+ layar fitur Hermes. Tema Terang (Pastel Clay) & Gelap (Synthetica AI) sesuai `DESIGN*.md` yang dilampirkan. Buka file ini langsung untuk preview interaktif (mode demo). |
| `android/app/src/main/assets/runtime/` | Skrip yang dieksekusi **di dalam** Ubuntu proot: bootstrap, install Hermes, services, doctor, dan `hermes_bridge.py` (JSON API untuk fitur yang tidak punya CLI langsung) |
| `android/app/src/main/jniLibs/arm64-v8a/` | ✅ **Sudah ada di workspace**: `libproot.so` 5.1.107.102 (aarch64), `libproot-loader.so`, `libtalloc.so.2`, `libandroid-shmem.so` |
| `android/app/src/main/assets/rootfs/` | ✅ **Sudah ada di workspace**: Ubuntu Base 24.04.5 arm64 + `/opt/arkax`, 2 bagian (24 MB + 3,9 MB) + `rootfs.sha256` |
| `android/app/src/main/assets/runtime/hermes-src.tar.gz` | ✅ **Sudah ada di workspace**: source Hermes `v0.23.1` pack *slim* (51 MB; `tests/`, `website/`, `contributors/`, `.github/`, `evals/`, `tests-js/`, `nix/` dibuang, **`apps/` tetap ada**) |
| `scripts/` | Pembuat rootfs, pengunduh proot & source Hermes, perakit aset, build APK, pemeriksa repositori |
| `docs/` | Arsitektur, peta **semua fitur** Hermes → layar/CLI, API jembatan, cara build, batasan proot |
| `.github/workflows/ci.yml` | Validasi sintaks shell / Python / JS / JSON setiap push |

### Status penting (baca ini dulu)

✅ **Sudah nyata di workspace ini**: seluruh source, skrip build, dokumentasi, UI interaktif, dan **tiga aset biner di atas** (total ≈ 80 MB). Verifikasi: `./scripts/check.sh` → semua aset terdeteksi; checksum gabungan rootfs cocok dengan `rootfs.sha256`.

ℹ️ **Berkas biner itu ada di workspace, tetapi sengaja di-`.gitignore`** supaya repo Git tetap ringan (`.git` ≈ 0,5 MB, 60 berkas ter-track) dan tidak melewati batas snapshot Arena. Kalau Anda `push` repo ini lalu `clone`, jalankan `./scripts/make-assets.sh` sekali untuk menghasilkannya kembali — atau `git add -f` / Git LFS bila memang ingin menyimpannya di remote. Selama masih di workspace ini, APK bisa langsung dirakit tanpa mengunduh apa pun.

⚠️ **Yang belum ada**: file **APK** jadi. Workspace ini tidak memiliki Android SDK/NDK, jadi perakitan terakhir (`gradlew assembleDebug`) harus dilakukan di mesin Anda.

⚠️ **Jujur soal offline**: rootfs Ubuntu **dan** source Hermes sudah offline di dalam APK. Tetapi Ubuntu Base tidak menyertakan Python/Node/git/ffmpeg, dan host build sandbox ini tidak punya proot aarch64 yang bisa dijalankan untuk memasangnya lebih dulu. Jadi **first-run membutuhkan jaringan sekali** untuk `apt-get` + `uv/pip` dependency; setelah itu `~/.hermes` dan environment Python tersimpan di rootfs dan aplikasi bisa dipakai offline (dengan model lokal/Ollama). Ingin first-run 100% offline? Jalankan `./scripts/build-rootfs.sh` di Linux yang punya `proot` (tanpa `--no-apt`) sehingga paket ikut terpanggang ke dalam rootfs, atau bundel wheel Python hasil `uv sync`. Lihat [docs/BUILD.md](docs/BUILD.md#4-bangun-rootfs-ubuntu-2404).

⚠️ **Catatan upstream per 16 Nov 2026**: paket APT resmi Hermes untuk Termux/AArch64 sedang diberi peringatan "currently broken" di dokumentasi resminya. Karena itu Arkaxhermes **tidak** memakai jalur APT Termux: ia memasang source rilis `v0.23.1` (atau tag yang Anda pin) di dalam Ubuntu proot glibc. Ini juga yang membedakan Arkaxhermes dari sekadar wrapper Termux.

---

## Mulai cepat

```bash
cd Arkaxhermes

# Workspace ini: aset sudah ada → langsung build (SDK 35 / NDK / JDK 17 / Gradle 8.9)
./scripts/build-apk.sh debug
adb install -r dist/Arkaxhermes-debug-0.1.0.apk

# Setelah clone repo Git (biner di-.gitignore): bangun aset dulu, baru APK
./scripts/make-assets.sh --arch arm64 --abi arm64-v8a --hermes-tag v0.23.1
```

Ingin lihat UI-nya tanpa build? Buka `android/app/src/main/assets/www/index.html` di viewer workspace — semua layar, tema, dan alur chat sudah interaktif memakai data demo.

Detail lengkap: [docs/BUILD.md](docs/BUILD.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/FEATURE_MAP.md](docs/FEATURE_MAP.md) · [docs/BRIDGE_API.md](docs/BRIDGE_API.md) · [docs/PROOTFS.md](docs/PROOTFS.md)

---

## Alur pertama kali (first run)

1. `MainActivity` menyalakan `ArkaxHttpServer` di `127.0.0.1:18789` dan memuat UI dari `http://127.0.0.1:18789/` (origin HTTP lokal → tidak ada masalah CORS `file://`).
2. `RootfsInstaller` menggabungkan `assets/rootfs/ubuntu-rootfs.tar.gz.part*`, memverifikasi SHA-256, lalu mengekstrak ke `filesDir/rootfs/ubuntu` dengan parser TAR di Kotlin (tidak bergantung pada `tar` di Android).
3. `ProotRuntime` menjalankan `/opt/arkax/bootstrap.sh` lewat `libproot.so` dari `nativeLibraryDir` (Android 10+ melarang eksekusi biner dari `filesDir`, jadi proot **harus** berada di `jniLibs`). `LD_LIBRARY_PATH` dan `PROOT_LOADER` diisi ke proses proot itu sendiri.
4. `install-hermes.sh` memasang dependency APT, mengekstrak `hermes-src.tar.gz` yang terlihat di `/opt/arkax` lewat bind mount, membuat wrapper `/usr/local/bin/hermes`, lalu `hermes doctor`.
5. UI menampilkan layar "Instalasi Ubuntu" dengan progres live (SSE); setelah `ready`, semua layar aktif. Gateway, cron ticker, dan dashboard bisa dijalankan sebagai foreground service.

Data pengguna (`~/.hermes/`: config, `.env`, MEMORY.md, USER.md, skills, sessions SQLite, cron, plugins) hidup di dalam rootfs → ikut ter-backup, bisa diekspor, dan terisolasi per **profile** Hermes.

---

## Peta fitur ringkas

| Fitur Hermes | Di Arkaxhermes |
| --- | --- |
| Agent loop + 40+ tools, toolsets, 6 terminal backend | Chat, Tools & Toolsets, Terminal |
| Skills (auto-create, self-improve, Skills Hub, agentskills.io) | Skills, Workspace |
| Memory 3 lapis (MEMORY.md/USER.md, FTS5 session search, Honcho) | Memori, Sesi & Riwayat, Workspace |
| Gateway Telegram/Discord/Slack/WhatsApp/Signal/Email/Home Assistant + voice memo | Gateway |
| Cron + webhook + no-agent mode + delivery | Cron & Otomasi |
| Delegasi subagen, code execution RPC, worktree, batch/trajectory | Delegasi, Code Execution, Batch & Trajektori |
| MCP, plugins, hooks, bot mode, profiles, context files, ACP | layar masing-masing di drawer |
| Nous Portal (300+ model + Tool Gateway), 40+ provider | Provider, Portal & Tool Gateway |
| TUI, slash command, `/model`, `/compress`, `/usage`, approval gate | Terminal, Chat, Persetujuan & Keamanan |

Tabel lengkap satu-per-satu ada di [docs/FEATURE_MAP.md](docs/FEATURE_MAP.md). Prinsipnya: **setiap** fitur dapat dijangkau, baik lewat kontrol UI khusus maupun lewat passthrough CLI/TUI yang sama persis dengan Hermes asli — tidak ada fitur yang hanya berupa mock.

---

## Audit kompatibilitas v0.23.1

Saya sudah menjalankan audit dua arah terhadap source Hermes yang dibundel: `hermes --help` + help subcommand, lalu render seluruh UI untuk mencocokkan tiap tombol ke handler/endpoint/CLI. Hasil akhir: **27 layar, 44 tombol, 0 dead button, 0 ikon hilang, 71 perintah CLI, 67 aksi bridge, 43 provider, 57 toolset + `stt`, 0 ERROR / 0 WARNING**.

Beberapa ketidaksesuaian awal (mis. `sessions list --json`, `mcp list --json`, `dashboard serve`, `config set provider`, `sessions.db`, `mcp.json`, backup `.tar.gz`) sudah diperbaiki. Rincian jujur, termasuk fitur yang tetap hanya bisa lewat Terminal/TUI dan batasan proot, ada di:

- [docs/AUDIT.md](docs/AUDIT.md) — laporan lengkap
- [docs/AUDIT.json](docs/AUDIT.json) — hasil mesin
- [docs/AUDIT_MATRIX.csv](docs/AUDIT_MATRIX.csv) — matriks per elemen
- [docs/CLI_CATALOG.md](docs/CLI_CATALOG.md) — 71 perintah `hermes`

Jalankan ulang kapan saja: `./scripts/check.sh` atau `python3 scripts/audit.py --strict`.

## Keamanan

- Kunci API disimpan terenkripsi (AES-GCM Android Keystore) di sisi native, lalu ditulis ke `~/.hermes/.env` di dalam rootfs dengan mode `600`. Kunci tidak pernah disimpan di `localStorage` WebView.
- Server jembatan hanya bind `127.0.0.1`, memeriksa header `X-Arkax-Token` (token acak per proses), dan menolak origin asing.
- Persetujuan eksekusi perintah (`approval gate`), `--safe-mode`, dan profil terisolasi tetap memakai mekanisme Hermes, tidak dilewati.
- proot **bukan** sandbox keamanan keras: tidak ada root, tidak ada namespace/seccomp penuh, dan proses bisa dihentikan Android saat layar mati. Lihat [docs/PROOTFS.md](docs/PROOTFS.md).

## Lisensi

Arkaxhermes: MIT (lihat [LICENSE](LICENSE)). Hermes Agent upstream: MIT © Nous Research. Ubuntu, proot, libtalloc, libandroid-shmem, dan paket lain tunduk pada lisensi masing-masing; atribusi dan tautan sumber ada di [docs/PROOTFS.md](docs/PROOTFS.md). Arkaxhermes adalah proyek tidak resmi dan tidak berafiliasi dengan Nous Research.
