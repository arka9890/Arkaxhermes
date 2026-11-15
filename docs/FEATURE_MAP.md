# Peta Fitur: Hermes Agent → Arkaxhermes

Referensi: [repo upstream](https://github.com/NousResearch/hermes-agent), [dokumentasi resmi](https://hermes-agent.nousresearch.com/docs/), rilis stabil yang dipin: `v0.23.1` (10 Nov 2026).

**Legenda mekanisme**

- `UI` — kontrol khusus di layar (toggle, form, daftar, editor) yang memanggil `hermes_bridge.py` / CLI.
- `CLI` — passthrough perintah asli Hermes lewat Terminal atau tombol "Jalankan" pada layar fitur; hasilnya ditampilkan apa adanya (stdout/stderr, streaming).
- `TUI` — Hermes `--tui` dijalankan di pseudo-TTY di dalam proot dan dialirkan ke layar Terminal.
- `CFG` — ditulis ke `~/.hermes/config.yaml` / `.env` lewat bridge, dipakai Hermes tanpa modifikasi kode upstream.
- `SVC` — proses panjang yang dijaga `AgentService` (foreground service + wake lock).

> Komitmen desain: **tidak ada fitur yang hanya berupa tampilan**. Jika upstream belum punya CLI/JSON untuk suatu fitur, Arkaxhermes membaca/menulis berkas konfigurasi aslinya (`hermes_bridge.py`) atau membuka TUI/CLI-nya. Source Hermes tidak di-fork dan tidak diubah.

---

## 1. Inti agent & percakapan

| Fitur Hermes | Mekanisme | Lokasi di Arkaxhermes | Perintah / berkas |
| --- | --- | --- | --- |
| Agent tool-calling loop (default 90 turn) | UI + CLI | Chat | `hermes chat --query-file -` (prompt lewat stdin, aman dari shell injection) |
| Streaming jawaban & preview eksekusi tool | UI (SSE) | Chat → panel "Aktivitas alat" | `/api/chat` membaca stdout baris-demi-baris |
| One-shot final answer only | CLI | Terminal / aksi cepat | `hermes -z "…"` |
| Resume sesi by id / judul / latest | UI | Chat, Sesi & Riwayat | `--resume`, `--continue`, `-c "<judul>" --create-if-missing` |
| Interrupt & redirect, `/stop` | UI | Chat (tombol Stop) | mengirim sinyal ke process + `hermes chat` baru |
| `/new`, `/reset`, `/retry`, `/undo` | UI | Chat (palet slash command) | slash command diteruskan ke sesi |
| `/compress`, `/usage`, `/insights` | UI + CLI | Chat, Statistik | slash command / `hermes insights` |
| `/model`, `/personality`, `/skills`, `/platforms` | UI | Chat + Provider + Skills | slash command |
| Personality & system prompt | UI + CFG | Workspace → Prompts & Instructions | `~/.hermes/` system prompts, `hermes config set` |
| Konteks: AGENTS.md, SOUL.md, `.cursorrules`, context files | UI + CFG | Context Files, Workspace | `hermes chat` auto-injection + `--image`, `--query-file` |
| Prompt caching, context compression, cache clock | CLI + UI | Statistik & Konteks | `/context`, `/compress`, `hermes chat --verbose` |
| Checkpoint filesystem, `--yolo`, `--safe-mode`, approval gate | UI | Persetujuan & Keamanan, Chat | flag diteruskan; antrean approval dibaca bridge |
| `--max-turns`, `--source`, `--pass-session-id` | CFG | Pengaturan lanjutan | dikirim oleh `HermesRuntime.streamChat` |

## 2. Tools, toolset & backend eksekusi

| Fitur | Mekanisme | Layar | Catatan |
| --- | --- | --- | --- |
| 40+ tools: `terminal`, `process`, `read_file`, `patch`, `write_file` | UI + CLI | Tools & Toolsets, Terminal | tool berjalan di Ubuntu proot |
| `web_search`, `web_extract`, `x_search` | UI + CFG | Tools & Toolsets, Portal | kunci lewat `.env` / Nous Tool Gateway |
| `browser_exec`, `browser_cdp`, `browser_dialog`, `browser_vault` | UI + CLI | Browser & Media | butuh Chromium di rootfs bila tersedia; WebView device bisa dipakai sebagai fallback tampilan |
| `vision_analyze`, `image_generate`, `text_to_speech`, transkrip voice memo | UI | Browser & Media, Gateway | lampiran gambar → `--image <path>`; audio → transkrip gateway |
| `todo`, `clarify`, `execute_code`, `delegate_task` | UI + CLI | Delegasi, Code Execution | RPC Python memanggil tools via Hermes |
| `memory`, `session_search`, `cronjob_manage` | UI | Memori, Sesi, Cron | lihat bagian 3/4 |
| Toolset: `web`, `search`, `terminal`, `file`, `browser`, `vision`, `image_gen`, `skills`, `tts`, `todo`, `memory`, `session_search`, `cronjob`, `code_execution`, `delegation`, `clarify`, `messaging`, `discord`, `discord_admin`, `debugging`, `safe`, preset `hermes-cli`/`hermes-telegram`, dinamis `mcp-<server>` | UI | Tools & Toolsets | toggle → `hermes tools` / `config.yaml`; `hermes chat --toolsets "..."` |
| Backend `local` (default) | UI | Terminal | = Ubuntu proot di perangkat |
| Backend `docker`, `ssh`, `modal`, `daytona`, `vercel_sandbox` | CFG + CLI | Terminal Backends | dikonfigurasi lewat `terminal.backend` + kredensial; layanan cloud butuh jaringan |
| Backend plugin `singularity`/`sprites` | CLI | Plugin | `hermes plugins install …` |
| Signal-death annotation, UTF-16 transcoding | CLI | Terminal | perilaku asli `read_file`/`terminal` tetap utuh |

> Catatan jujur: daemon Docker/KVM **tidak** bisa berjalan tanpa root di Android. Backend `docker` hanya berguna bila diarahkan ke daemon jarak jauh; `ssh`/`modal`/`daytona`/`vercel_sandbox` adalah jalur yang realistis untuk isolasi penuh di perangkat.

## 3. Learning loop: skills, memory, sesi

| Fitur | Mekanisme | Layar | Sumber data |
| --- | --- | --- | --- |
| Skills markdown + YAML frontmatter, agentskills.io | UI | Skills, Workspace | `~/.hermes/skills/` |
| Skill auto-creation setelah tugas kompleks | UI + CFG | Skills (nudge) | `config.yaml` + notifikasi bridge |
| Skill self-improvement saat dipakai | UI | Skills (riwayat revisi) | berkas skill |
| Skills Hub / install & share | CLI | Skills | `hermes skills`, `hermes plugins`, agentskills.io |
| Preload skill `-s` | UI | Chat, Skills | `hermes chat -s …` |
| 3 lapis memori: sesi / fakta / prosedural | UI | Memori | `MEMORY.md`, `USER.md`, SQLite, skills |
| Periodic memory nudge | UI + CFG | Memori | `hermes config set` |
| Honcho dialectic user modeling (12 layer) | CLI + CFG | Memori → Penyedia Memori | `hermes plugins install honcho`, `hermes memory-providers` |
| Injection/exfiltration scanning pada memori | CFG | Persetujuan & Keamanan | bawaan Hermes, tidak dimatikan |
| Session store SQLite WAL + FTS5 | UI | Sesi & Riwayat | `hermes_bridge.py` mencari `*.db` di `~/.hermes` lalu `SELECT … FROM … MATCH` dengan fallback `LIKE` |
| Cross-session recall + ringkasan LLM | UI | Sesi & Riwayat (cari) | `session_search` tool |
| Token, biaya, model per sesi | UI | Statistik | tabel sesi |

## 4. Otomasi & orkestrasi

| Fitur | Mekanisme | Layar | Perintah |
| --- | --- | --- | --- |
| Cron natural language & ekspresi | UI + CLI | Cron & Otomasi | `hermes cron create/list/pause/resume/run/remove`, `/cron add` |
| `cronjob_manage` (single action-style tool) | CLI | Cron & Otomasi | dipanggil agent lewat chat |
| One-shot/recurring, pause/edit/trigger/remove, stop run in-flight | UI | Cron & Otomasi | `hermes cron …` + `~/.hermes/cron/jobs.json` |
| Attach skill ke job, multi-skill | UI | Cron & Otomasi | `--skill` |
| Delivery ke origin chat / file / platform | UI | Cron & Otomasi, Gateway | `hermes send`, gateway notifier |
| No-agent mode (script only, 0 LLM) | UI | Cron & Otomasi | `hermes cron create --no-agent` |
| Webhook + event-triggered cron | SVC + UI | Cron & Otomasi, Gateway | `hermes gateway run`, rute webhook |
| Model/reasoning pin per job, `cron.model` | UI | Cron & Otomasi | `--pin`, `--model`, `--reasoning-effort`, `hermes config set cron.model` |
| Admission recovery / durable delivery | SVC | Status Layanan | scheduler Hermes + `AgentService` |
| Delegasi subagen (isolated, max depth 2, 3 concurrent) | UI + CFG | Delegasi | `delegate_task`, `Settings → Model → Subagents` equivalent → `config.yaml` |
| Python RPC / `execute_code` (zero-context-cost) | UI | Code Execution | skrip di `/mnt/arkax/scripts`, dijalankan lewat Terminal |
| Git worktree `-w`, `worktree list/prune/restore`, stale sweep 6 jam | CLI | Code Execution, Terminal | `hermes -w`, `hermes worktree …` |
| Batch processing | UI | Batch & Trajektori | `hermes batch` / skrip rootfs |
| Trajectory JSONL, compression, Atropos RL | UI + CLI | Batch & Trajektori | `hermes trajectory …` (nama subcommand mengikuti rilis) |
| Hooks (event-driven, `on_session_open`, `post_curator_run`, plugin hooks) | CFG | Hooks | `~/.hermes/hooks/`, plugin API |
| Bot Mode: named bots, routines, group chats, @mentions | UI + CFG | Bot Mode | konfigurasi gateway/Desktop-compatible |
| Profil terisolasi (`HERMES_HOME`) | UI | Profil | `--profile`, `hermes profile use`, direktori terpisah |

## 5. Gateway & platform

| Platform | Mekanisme | Layar |
| --- | --- | --- |
| Telegram, Discord, Slack, WhatsApp, Signal | SVC + UI | Gateway |
| Email, Home Assistant, WeChat (HermesClaw), iMessage/BlueBubbles | SVC + UI | Gateway, Plugin |
| Voice memo transcription & kontinuitas lintas platform | SVC | Gateway |
| `hermes gateway setup/start/run/attach`, `/platforms`, `/status`, `/sethome`, DM pairing | CLI + UI | Gateway, Terminal |
| `hermes send` one-shot ke platform | UI | Gateway |
| Webhook inbound + event cron | SVC | Gateway, Cron |
| Notifikasi lokal Android saat ada pesan/approval | SVC | Pengaturan, Persetujuan |

## 6. Integrasi, model & ekosistem

| Fitur | Mekanisme | Layar |
| --- | --- | --- |
| Nous Portal: 300+ model, OAuth, `hermes setup --portal`, `hermes portal info` | UI + CLI | Portal & Tool Gateway, Provider |
| Tool Gateway: web search (FAL image gen, OpenAI TTS, Browser Use) | UI + CFG | Portal & Tool Gateway |
| Provider: OpenRouter, OpenAI, Anthropic, Gemini, DeepSeek, xAI, Bedrock, Azure, Kimi, MiniMax, Qwen, Z.ai, Novita, HuggingFace, Ollama, LM Studio, Copilot/ACP, Nous, custom endpoint | UI + CFG | Provider (kartu + kunci + latensi + model) |
| Keyword-based cheap/strong model routing, fallback chain | UI + CFG | Provider → Routing |
| MCP client (stdio + HTTP, auto-reconnect, OSV check, credential stripping) | UI + CLI | MCP |
| Plugin system + katalog (Home Assistant, Camofox, Honcho, Singularity, sprites …) | UI + CLI | Plugin |
| ACP adapter (`hermes-acp`) | CLI | Integrasi IDE, Terminal |
| Dashboard / Webapp / Desktop connection sharing | SVC + UI | Status Layanan (`hermes dashboard`) |
| Import dari OpenClaw / agent lain, migrasi | CLI | Pengaturan → Impor |
| `/insights`, usage, kuota token, biaya | UI | Statistik |

## 7. Operasional aplikasi (tambahan Arkaxhermes, bukan fitur upstream)

| Fitur | Layar | Implementasi |
| --- | --- | --- |
| First-run installer proot + progress live (SSE) | Instalasi Ubuntu | `RootfsInstaller` + `bootstrap.sh` |
| Verifikasi SHA-256 rootfs & source Hermes | Instalasi Ubuntu | `rootfs/manifest.json` |
| Tema Terang / Gelap / Sistem (dua design system lampiran) | Pengaturan, semua layar | CSS variable + `SettingsStore` |
| Ukuran font, haptic feedback, simpan riwayat otomatis | Pengaturan | `SettingsStore` + `JsBridge` |
| Kunci API terenkripsi | Pengaturan, Provider | Android Keystore AES-GCM → `~/.hermes/.env` (0600) |
| Enkripsi obrolan lokal, ekspor `.json`/`.md`, hapus cache | Pengaturan | `hermes_bridge.py` + `JsBridge.share` |
| Monitor CPU/RAM/suhu/disk | Pengaturan, Status Proot | `/proc`, `/sys`, `Runtime` |
| Terminal rootfs, `hermes doctor`, log, update | Terminal, Log & Doctor | `/api/exec` |
| Backup/restore seluruh `~/.hermes` | Backup | tar via bridge |
| Foreground service, wake lock, pengecualian baterai, boot receiver | Status Layanan | `AgentService`, `BootReceiver` |
| Lampiran dokumen/gambar, dikte suara, salin kode, bagikan teks | Chat | SAF + `JsBridge` + `/mnt/arkax/inbox` |

---

## Yang secara fisik tidak bisa identik di Android non-root

| Fitur upstream | Status | Alasan & pengganti |
| --- | --- | --- |
| Docker daemon lokal / KVM microVM | Tidak tersedia | butuh root/kernel; pakai `ssh`, `modal`, `daytona`, `vercel_sandbox`, atau `docker` ke daemon remote |
| Electron Desktop, bundled Chromium, computer-use tools | Tidak dibundel | UI Arkaxhermes menggantikan Desktop; `browser_*` butuh Chromium di rootfs atau browser cloud |
| Termux:API microphone/clipboard native | Diganti | `JsBridge` + Android Speech/SAF |
| `nemo-relay` exporter | Tidak dibundel | tidak tersedia untuk target Android upstream |
| Proses background permanen | Best effort | Android dapat membunuh proses; foreground service + wake lock + exemption, dengan peringatan di UI |
| `sys.platform == "linux"` | Ya (glibc Ubuntu) | keunggulan proot Ubuntu dibanding paket Termux yang melaporkan `android` |

Daftar ini sengaja eksplisit: "semua fitur diimplementasikan" berarti **semua bisa dijangkau dan dioperasikan**, dengan pengganti yang jujur untuk kemampuan yang mustahil tanpa root. Rincian teknis ada di [docs/PROOTFS.md](docs/PROOTFS.md).
