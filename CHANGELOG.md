# Changelog

## 0.1.0 — 16 November 2026

- Repo **Arkaxhermes** dibuat: aplikasi Android untuk [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) dengan Ubuntu 24.04 proot yang dibundel di APK.
- Pin upstream: Hermes Agent `v0.23.1` (rilis stabil 10 Nov 2026), Ubuntu Base `24.04.5`.
- Native Kotlin: `MainActivity` + WebView, `ArkaxHttpServer` (loopback + token), `RootfsInstaller` (parser TAR/GZIP + SHA-256), `ProotRuntime`, `HermesRuntime`, `AgentService`, `KeyVault` (Android Keystore), `SettingsStore`, `BootReceiver`.
- UI mandiri `assets/www/index.html`: Chat, Provider, Workspace, Terminal, Pengaturan + 20+ layar fitur Hermes; tema Terang (Pastel Clay) & Gelap (Synthetica AI) sesuai desain lampiran; mode demo offline untuk preview.
- `hermes_bridge.py`: aksi JSON untuk skills, memory, sesi FTS5, cron, MCP, tools, plugin, profil, approval, hooks, backup — dengan fallback CLI bila upstream tidak menyediakan subcommand.
- Skrip build: `fetch-proot.sh`, `fetch-hermes-src.sh`, `build-rootfs.sh`, `make-assets.sh`, `build-apk.sh`, `check.sh`; CI validasi sintaks.
- Dokumentasi: arsitektur, peta seluruh fitur, API jembatan, panduan build, dan batasan jujur proot/Android non-root.

### Aset biner yang sudah ikut di repo
- `jniLibs/arm64-v8a/`: `libproot.so` 5.1.107.102 aarch64 + `libproot-loader.so`, `libtalloc.so.2(.5.0)`, `libandroid-shmem.so` (paket Termux).
- `assets/rootfs/`: Ubuntu Base 24.04.5 arm64 + `/opt/arkax`, 2 bagian (28 MB) dengan `rootfs.sha256` terverifikasi.
- `assets/runtime/hermes-src.tar.gz`: source Hermes `v0.23.1` pack slim (51 MB, `apps/` tetap ada).

### Belum termasuk (dihasilkan di mesin build)
APK akhir dan dependency APT/Python yang dipanggang ke rootfs — keduanya butuh Android SDK/NDK dan proot aarch64 di host. Lihat [docs/BUILD.md](docs/BUILD.md).
