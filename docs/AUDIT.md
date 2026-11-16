# Audit kompatibilitas Arkaxhermes ↔ Hermes Agent `v0.23.1`

**Tanggal:** 16 November 2026  
**Sumber yang diaudit:** `android/app/src/main/assets/runtime/hermes-src.tar.gz` — source rilis `v0.23.1` yang memang dibundel di workspace ini, diekstrak ke `/tmp/hermes-audit`. Bukan sekadar README atau dokumentasi web.

## Ringkasan eksekutif

Pertanyaan: *"sudah sesuai sama repo Hermes-nya belum? cek setiap element, tombol dan semuanya."*

**Jawaban jujur: sebelum audit ini, belum semuanya cocok.** Ada perintah CLI yang tidak ada di `v0.23.1`, path data yang keliru, tombol yang hanya menampilkan toast, dan beberapa pengaturan yang belum berdampak. Semua temuan yang bisa diperbaiki sudah saya perbaiki. Hasil akhir:

| Pemeriksaan | Hasil |
| --- | --- |
| `python3 hermes --help` dari source bundel | ✅ 71 perintah tingkat atas |
| Subcommand dari parser builder + `<command> --help` | ✅ 309 nama subcommand terdeteksi; katalog ringkas di [CLI_CATALOG.md](CLI_CATALOG.md) |
| Layar UI | ✅ 27 layar dirender di Node VM |
| `data-act` / tombol | ✅ 44 aksi tampil, **44 handler**, **0 dead button** |
| Ikon SVG | ✅ 32 ikon dipakai, 56 path tersedia, **0 ikon hilang** |
| Aksi `hermes_bridge.py` | ✅ 67 aksi, semuanya terpetakan ke UI/CLI/TUI |
| Provider | ✅ 43 entri dari `hermes_cli/auth.py` + `models_catalog_static.py` + alias lokal |
| Toolset | ✅ 57 toolset dari `toolsets.py` + `stt` config-only |
| Endpoint HTTP | ✅ 7 path dipakai UI, 19 path tersedia di `ArkaxHttpServer.kt` |
| `window.ArkaxBridge` | ✅ 17 metode, semua panggilan JS tersedia di Kotlin |
| `./scripts/audit.py --strict` | ✅ **0 ERROR, 0 WARNING** |
| `./scripts/check.sh` | ✅ lulus |

Bukti mesin: [AUDIT.json](AUDIT.json) · Matriks per elemen: [AUDIT_MATRIX.csv](AUDIT_MATRIX.csv)

---

## Metode

1. Ekstrak source Hermes `v0.23.1` dari aset APK yang dibundel.
2. Pasang dependency parser di sandbox (`ruamel.yaml`, `python-dotenv`, `fire`) lalu **jalankan langsung**:
   - `python3 hermes --help`
   - 71× `python3 hermes <command> --help`
   - 30+ `python3 hermes <command> <subcommand> --help` untuk chat, config, cron, gateway, sessions, tools, mcp, plugins, skills, approvals, hooks, backup, import, send, worktree, portal.
3. Bandingkan argumen `hermes_bridge.py`, `services.sh`, `HermesRuntime.kt`, dan `SCREENS.cmds` dengan help di atas.
4. Render **setiap layar** memakai VM Node + DOM stub, kumpulkan semua `data-act`, lalu cocokkan ke `case` handler klik/change. Termasuk drawer, form, modal hapus data, overlay instalasi, slash command, pencarian workspace, dan katalog CLI.
5. Parse AST `ACTIONS`, `PROVIDERS`, `TOOLSETS`; parse regex endpoint Kotlin, `@JavascriptInterface`, dan panggilan `BRIDGE.*`.

Skrip audit permanen: `scripts/audit.py`, `scripts/audit-ui.js`, dipanggil otomatis oleh `scripts/check.sh`.

---

## Temuan awal yang **tidak cocok**, dan perbaikannya

### 1. Perintah CLI yang keliru

| Sebelum | Kenyataan di `v0.23.1` | Perbaikan |
| --- | --- | --- |
| `hermes sessions list --json` | tidak ada `--json`; `sessions list` hanya `--source/--limit/--workspace` | baca langsung `~/.hermes/state.db` (tabel `sessions`, `messages`), fallback teks `hermes sessions list` |
| `hermes sessions show <id> --json` | subcommand `show` tidak ada | baca pesan dari `state.db`; ekspor memakai `hermes sessions export --session-id … --format md --yes` |
| `hermes sessions search <q> --json` | subcommand `search` tidak ada | FTS5 asli: `messages_fts` / `messages_fts_trigram` JOIN `messages`; fallback `LIKE` |
| `hermes cron list --json` | tidak ada `--json` | baca `~/.hermes/cron/jobs.json`, normalisasi `schedule.display`, `enabled`, `next_run_at` |
| `hermes cron create … --no-agent` tanpa script | upstream menolak: butuh `--script` | validasi + field `script`; pesan error menjelaskan aturan |
| `hermes mcp list --json` | tidak ada `--json` | `hermes mcp list` + `hermes config get mcp_servers --json` |
| `hermes tools --json` | tidak ada flag itu | `hermes tools list --platform cli`; parse baris `✓ enabled` / `✗ disabled` |
| `hermes config set toolsets …` | bentuk resmi per-platform lewat `hermes tools enable/disable` | `tools.set` memanggil `tools disable`+`enable`, dan `config set stt.enabled` untuk toolset config-only |
| `hermes config set provider …` / `model …` | kunci resmi `model.provider` / `model.default` | `model.set` diperbaiki + alias `openai→openai-api`, `qwen→alibaba`, dll. |
| `hermes config get memory.nudge` | kunci resmi `memory.nudge_interval` | `skills.nudges` + `hermes memory status` |
| `hermes approvals approve/deny <id>` | tidak ada; hanya `approvals suggest`/`test` | keputusan dicatat lokal + `ok:false` + fallback eksplisit ke `hermes --tui` |
| `hermes dashboard serve` | `serve` adalah perintah **top-level**, bukan subcommand dashboard | `hermes serve --host 127.0.0.1 --port 9119 --skip-build` |
| `hermes cron ticker` | tidak ada; scheduler bawaan 60 detik, CLI satu tick bernama `cron tick` | loop `hermes cron tick --accept-hooks` di `services.sh` |
| `hermes send telegram "pesan"` | `send` butuh `-t/--to` | `hermes send -t <platform> <pesan>` |
| `hermes batch --help`, `hermes trajectory --help` | tidak ada subcommand `batch`/`trajectory` | `python3 /opt/hermes-agent/batch_runner.py` + `hermes sessions export --format trace` |
| `hermes profile list --json`, `hermes --profile … chat` | `profile list` tanpa `--json`; `--profile` bukan flag help top-level | `hermes profile list/create/use/show` |
| `hermes config set delegation.max_depth`, `security.approval` | kunci tidak ada | `delegation.max_spawn_depth`, `delegation.max_concurrent_children`, `security.approval.transport` |
| `python -m hermes_cli` (fallback installer) | paket tidak punya `__main__.py` | fallback memanggil `python <source>/hermes` dengan `PYTHONPATH` |
| Chat streaming tanpa `-Q/--oneshot` | output bisa campur banner/spinner | `-Q --oneshot --format text` (sengaja **tidak** memakai `stream-json`, karena rilis ini merutekannya lewat gateway) |
| Beberapa `--image` sekaligus | `--image` singular, bukan append | kirim gambar pertama + log peringatan |
| `session_id:` hanya dibaca dari stdout | `-Q` mencetaknya ke stderr | parser sesi juga membaca stderr |
| `PROOT_LOADER` ditaruh di `env -i` dalam rootfs | harus jadi environment proses **proot sendiri** | dipindah ke `ProcessBuilder.environment()` |

### 2. Path / format data yang keliru

| Sebelum | Kenyataan di upstream | Perbaikan |
| --- | --- | --- |
| `sessions.db` | `~/.hermes/state.db` dengan `sessions`, `messages`, `messages_fts` | `state_db()` + SQL sesuai `hermes_state_common.py` |
| `~/.hermes/mcp.json` | `mcp_servers:` di `config.yaml` | `hermes config set mcp_servers.<name> '<json>' --force` / `config unset` |
| `~/.hermes/bots.json` | Bot Mode adalah fitur gateway/Desktop plugin, bukan berkas JSON bernama itu | tetap disimpan sebagai indeks lokal **dengan catatan jujur**, aksi lanjutan lewat `hermes gateway`/`profile`/`peer` |
| `context-files.json` | AGENTS.md/SOUL.md/.cursorrules disuntikkan otomatis; tidak ada registry resmi | tetap indeks UI, diberi label "indeks Arkaxhermes" |
| `approvals/*.json` | antrean approval live ada di proses TUI/gateway | keputusan lokal + `hermes approvals suggest --json` |
| `~/.hermes/hooks/*.py` | `hooks.<event>` di `config.yaml`, consent di `shell-hooks-allowlist.json` | `hooks.set` menulis config lewat `hermes config set --force`; `hooks.list` memanggil `hermes hooks list` |
| `~/.hermes-<nama>` untuk profil | `~/.hermes/profiles/<nama>` | `hermes profile create/use/list` |
| backup `.tar.gz` | `hermes backup` menghasilkan **ZIP**, restore `hermes import` | `backup.create` → `hermes backup -o …`; `backup.restore` → `hermes import --force …` |
| `backup -q` untuk file `-o` | `-q` mengabaikan `-o`, menulis `~/state-snapshots` | default backup penuh; `quick` diberi catatan eksplisit |
| Layar Backup otomatis membuat backup saat dibuka | aksi destruktif/berat harus dipicu tombol | `backups.list` (read-only) + tombol `feature-run backup.create` |

### 3. UI: elemen, tombol, pengaturan

| Temuan | Perbaikan |
| --- | --- |
| `do-clear` tidak punya handler | ditambahkan; menghapus riwayat terenkripsi **dan** localStorage |
| `folder-menu` / `file-menu` hanya toast | `folder-menu` membuka direktori; `file-menu` membuka modal Buka / Ekspor / Hapus yang memanggil `files.read/delete` |
| Workspace memakai `demoFolders` terus, tidak pernah `files.list` | `loadFeatureFor('workspace')` + normalisasi entri `files.list` asli, tombol naik direktori, muat ulang |
| Provider memakai 8 entri hardcoded, tidak pernah `providers.list` | katalog 43 entri + `loadFeatureFor('provider')` saat boot |
| Filter `Cloud AI` / `Lokal (Ollama)` salah logika | filter diperbaiki |
| Toggle provider hanya mengubah state demo | nonaktif → `env.delete`; aktif → form kunci atau `hermes auth add <oauth>` |
| `haptics` diabaikan | `haptic()` kini menghormati `settings.haptics` |
| `fontSize` tidak berdampak | CSS memakai `--font-size`, `applyFont()` dipanggil saat boot/change/render |
| `autoSave` / `encryptLocal` tidak berdampak | `persistState()` menyimpan riwayat ke `localStorage` atau **Android Keystore AES-GCM** lewat `ArkaxBridge.securePut/secureGet/secureDelete`; `restoreState()` saat boot |
| `gateway.status` tidak ada di bridge | aksi baru + `hermes gateway status` + `demoPlatforms` |
| `feature-load` / form aksi tertentu fallback demo generik | 18 aksi demo eksplisit ditambahkan agar preview tidak sekadar "info" |
| Ikon `download` hilang | path SVG ditambahkan; audit ikon jadi 0 missing |
| `status` layanan memulai foreground service | `HermesRuntime.service(status)` langsung menjalankan `services.sh status` di proot |
| `tty` quoting rentan | `quoteArg()` escape single-quote dengan benar |
| `services.sh` memakai perintah yang tidak ada | ditulis ulang sesuai help: `gateway run`, `cron tick`, `serve`, `gateway status`, `cron status`, `webhook list` |
| Tidak ada cara menjangkau 71 perintah CLI dari UI | layar **Katalog CLI** + `docs/CLI_CATALOG.md`, tiap perintah/subcommand punya tombol `hermes … --help` |

### 4. Katalog yang sebelumnya terlalu sempit

- Provider: 8 → **43** (35 registry + canonical + alias `openai`, `qwen`, `ollama`, `custom`, `copilot`, dst.), dengan `envKeys` benar dan deteksi `auth.json` untuk OAuth/SDK.
- Toolset: 21 → **57** nama dari `toolsets.py` + `stt` config-only. `messaging` (tidak ada di `toolsets.py`) dibuang.
- Default toolset: `web,terminal,skills` → **`hermes-cli`** (bundle inti resmi, agar 40+ tools tidak terpotong).

---

## Yang **tidak** saya klaim sebagai "sama persis"

Ini penting supaya tidak muncul kesan bahwa semua fitur desktop Hermes sudah direimplementasikan ulang di WebView:

1. **Fitur interaktif tetap lewat passthrough.** `hermes model`, `hermes tools` interaktif, `hermes setup`, TUI, dashboard/Desktop, ACP, approval prompt live, dan OAuth device-code tidak dibuat ulang sebagai UI Android. Arkaxhermes menyediakan Terminal + pseudo-TTY (`script -q -c`) + `/api/exec` + katalog CLI, sesuai prinsip [FEATURE_MAP.md](FEATURE_MAP.md): **UI / CLI / TUI / CFG / SVC**.
2. **Approval decide tidak ada CLI** di `v0.23.1`. Tombolnya sekarang jujur: mencatat keputusan lokal, mengembalikan `ok:false`, dan membuka fallback TUI — bukan berpura-pura berhasil.
3. **Bot Mode, hosted rooms, group chat, Desktop plugin** sebagian besar hidup di `apps/desktop` + gateway. Layar Bot Mode Arkaxhermes adalah indeks lokal; konfigurasi penuh tetap lewat `hermes profile/gateway/peer` atau Desktop/TUI.
4. **Browser/CDP, Docker daemon, KVM, computer-use native** tidak bisa berjalan penuh di proot Android non-root. Terminal backend remote (`ssh`, `modal`, `daytona`, `vercel_sandbox`) dan Tool Gateway Nous tetap tersedia.
5. **Mode demo di viewer** memakai data contoh; hanya saat berjalan di APK dengan `ArkaxBridge` aktif yang memanggil rootfs/CLI asli.
6. **APK masih belum dirakit** di sandbox ini (tidak ada Android SDK/NDK). Audit ini memverifikasi source, bukan biner hasil `gradlew`.

---

## Cara mengulang audit

```bash
cd Arkaxhermes
./scripts/check.sh                 # termasuk audit strict
python3 scripts/audit.py --strict  # ringkasan + docs/AUDIT.json + AUDIT_MATRIX.csv
node scripts/audit-ui.js           # JSON hasil render semua layar
```

Untuk memverifikasi langsung terhadap upstream di mesin dengan dependency parser:

```bash
tar -xzf android/app/src/main/assets/runtime/hermes-src.tar.gz -C /tmp/hermes-audit
cd /tmp/hermes-audit/hermes-agent-0.23.1
python3 hermes --help
python3 hermes chat --help
python3 hermes config set --help
```

---

## Kesimpulan

**Sudah jauh lebih sesuai, tapi tidak pernah saya klaim "100% identik" dengan seluruh repo Hermes.** Yang benar:

- ✅ **Semua 71 perintah tingkat atas** dan subcommand yang dipakai Arkaxhermes kini diverifikasi terhadap help source `v0.23.1`.
- ✅ **Semua tombol/elemen UI yang dirender** punya handler; tidak ada dead button, tidak ada ikon hilang.
- ✅ **Semua aksi bridge** punya implementasi nyata atau fallback CLI/TUI yang jujur.
- ✅ Path data, format backup, kunci config, provider, toolset, dan layanan sudah diselaraskan dengan source upstream.
- ⚠️ Fitur yang memang interaktif/desktop/bergantung kernel tetap dijangkau lewat Terminal/TUI/CLI, bukan ditiru dengan mock.
- ⚠️ APK akhir tetap harus dirakit di mesin dengan Android SDK/NDK.
