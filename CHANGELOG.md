## 0.2.0 — 16 November 2026 (browser bawaan)

- Tambah `agent-browser v0.43.0` dari vercel-labs: binary Rust CLI linux-arm64 + daemon CDP, diverifikasi SHA-256.
- Tambah Chrome for Testing 157.0.8103.78 linux-arm64 sebagai install-time asset pack `browser_pack`; `fetch-agent-browser.sh` + `build-apk.sh --stage-assets`.
- Tab **Browser** baru di bottom nav: live WebSocket viewport `9223`, input mouse/touch/keyboard, URL bar, Back/Forward/Reload, Snapshot, Screenshot, Tabs, Start/Stop/Status, Dashboard `4848`.
- `BrowserRuntime.kt` mengekstrak Chrome ZIP dari asset pack, menulis wrapper `--no-sandbox`, dan menjalankan CLI lewat `/usr/local/bin/agent-browser`.
- Endpoint `/api/browser/*`, aksi `browser.*` di `hermes_bridge.py`, service `browser` di `AgentService`/`BootReceiver`, serta `ArkaxBridge.openBrowserDashboard()`.
- `bootstrap.sh`, `services.sh`, `doctor.sh`, `AGENTS.md` skill, manifest, Gradle asset pack, `.gitignore`, dan audit (`28 layar / 57 tombol / 74 aksi / 0 ERROR`) diperbarui.

## 0.1.1 — 16 November 2026 (audit kompatibilitas)

- Audit menyeluruh terhadap source Hermes `v0.23.1`: `hermes --help`, 71 perintah top-level, dan help subcommand dijalankan langsung dari source bundel.
- Perbaiki CLI yang tidak ada di upstream: `sessions show/search --json`, `cron list --json`, `mcp list --json`, `tools --json`, `dashboard serve`, `cron ticker`, `send <platform>`, `approvals approve/deny`, `batch/trajectory`, `--profile`, dll.
- Selaraskan path/format: `state.db` + FTS5, `cron/jobs.json`, `mcp_servers` di `config.yaml`, `hooks.<event>`, `profiles/<name>`, backup ZIP + `hermes import`.
- Perbaiki katalog: 43 provider, 57 toolset `toolsets.py` + `stt`, default `hermes-cli`, kunci `model.provider`/`model.default`, `memory.nudge_interval`, `delegation.max_spawn_depth`.
- Chat: `-Q --oneshot --format text`, satu `--image`, sesi dari stderr, TTY quoting aman, status layanan tanpa foreground service.
- UI: semua tombol berhandler, `do-clear`, aksi berkas nyata, Workspace/Provider memuat data proot, filter provider, `autoSave`/`encryptLocal` lewat Android Keystore, `haptics`, `--font-size`, ikon `download`, layar **Katalog CLI**.
- Tambah `scripts/audit.py`, `scripts/audit-ui.js`, `docs/AUDIT.md`, `docs/AUDIT.json`, `docs/AUDIT_MATRIX.csv`, `docs/CLI_CATALOG.md`; `check.sh` kini menjalankan audit strict.

# Changelog

## 0.1.0 — 16 November 2026

- Repo **Arkaxhermes** dibuat: aplikasi Android untuk [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) dengan Ubuntu 24.04 proot yang dibundel di APK.
- Pin upstream: Hermes Agent `v0.23.1` (rilis stabil 10 Nov 2026), Ubuntu Base `24.04.5`.
- Native Kotlin: `MainActivity` + WebView, `ArkaxHttpServer` (loopback + token), `RootfsInstaller` (parser TAR/GZIP + SHA-256), `ProotRuntime`, `HermesRuntime`, `AgentService`, `KeyVault` (Android Keystore), `SettingsStore`, `BootReceiver`.
- UI mandiri `assets/www/index.html`: Chat, Provider, Workspace, Terminal, Pengaturan + 20+ layar fitur Hermes; tema Terang (Pastel Clay) & Gelap (Synthetica AI) sesuai desain lampiran; mode demo offline untuk preview.
- `hermes_bridge.py`: aksi JSON untuk skills, memory, sesi FTS5, cron, MCP, tools, plugin, profil, approval, hooks, backup — dengan fallback CLI bila upstream tidak menyediakan subcommand.
- Skrip build: `fetch-proot.sh`, `fetch-hermes-src.sh`, `build-rootfs.sh`, `make-assets.sh`, `build-apk.sh`, `check.sh`; CI validasi sintaks.
- Dokumentasi: arsitektur, peta seluruh fitur, API jembatan, panduan build, dan batasan jujur proot/Android non-root.

### Aset biner yang sudah ada di workspace (di-.gitignore, dibuat ulang oleh `make-assets.sh`)
- `jniLibs/arm64-v8a/`: `libproot.so` 5.1.107.102 aarch64 + `libproot-loader.so`, `libtalloc.so.2(.5.0)`, `libandroid-shmem.so` (paket Termux).
- `assets/rootfs/`: Ubuntu Base 24.04.5 arm64 + `/opt/arkax`, 2 bagian (28 MB) dengan `rootfs.sha256` terverifikasi.
- `assets/runtime/hermes-src.tar.gz`: source Hermes `v0.23.1` pack slim (51 MB, `apps/` tetap ada).

### Belum termasuk (dihasilkan di mesin build)
APK akhir dan dependency APT/Python yang dipanggang ke rootfs — keduanya butuh Android SDK/NDK dan proot aarch64 di host. Lihat [docs/BUILD.md](docs/BUILD.md).
