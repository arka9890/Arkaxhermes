> **Audit 16 Nov 2026:** daftar aksi final diverifikasi terhadap source `v0.23.1`; lihat [AUDIT.md](AUDIT.md). `hermes_bridge.py` kini punya 67 aksi, termasuk `gateway.status`, `backups.list`, `cron.status`, `cron.tick`, `sessions.export`, `files.mkdir`.

# Arkax Bridge API

Server lokal: `http://127.0.0.1:18789` (port 18789–18799 dicoba berurutan; port aktif dikirim ke UI lewat `JsBridge.port()`). Semua respons `Content-Type: application/json; charset=utf-8`, kecuali aset statis dan SSE.

## Autentikasi

`MainActivity` membuat token acak 32 byte per proses. UI menerimanya lewat `JsBridge.token()` dan menyertakannya pada setiap permintaan:

```
X-Arkax-Token: <hex>
Origin: http://127.0.0.1:18789
```

Permintaan tanpa token, dengan origin asing, atau dari antarmuka non-loopback ditolak `403`. Endpoint statis `/`, `/index.html`, `/favicon.svg` tidak memerlukan token agar WebView bisa memuat halaman pertama.

## Aset statis

| Method | Path | Isi |
| --- | --- | --- |
| GET | `/`, `/index.html` | `assets/www/index.html` (SPA mandiri, tanpa CDN) |
| GET | `/favicon.svg` | ikon vektor inline |
| GET | `/health` | `{ok:true, app:"Arkaxhermes", version:"0.1.0"}` |

## Status & instalasi

### `GET /api/status`
```json
{
  "ok": true,
  "state": "ready",            // "not_installed" | "extracting" | "installing" | "ready" | "error"
  "rootfs": {"present": true, "sizeBytes": 987654321, "release": "Ubuntu 24.04.5 LTS", "arch": "arm64"},
  "proot": {"binary": "/data/app/.../lib/arm64/libproot.so", "loader": true},
  "hermes": {"version": "0.23.1", "home": "/root/.hermes", "installed": true},
  "services": {"gateway": "running", "cron": "stopped", "dashboard": "stopped"},
  "system": {"cpuLoad": 32, "ramUsedMb": 4300, "ramTotalMb": 12288, "tempC": 42, "diskFreeMb": 8192},
  "model": {"provider": "anthropic", "name": "claude-sonnet-4.5", "context": 200000},
  "token": "…" 
}
```

### `POST /api/install`
Body: `{"force": false}` · Memulai ekstraksi + bootstrap di thread background. Respons langsung `{ok:true, started:true}`. Progres dialirkan lewat SSE.

### `GET /api/install/stream` (SSE)
```
event: progress
data: {"step":"extract","percent":42,"message":"Menulis usr/bin/python3 …"}

event: log
data: {"line":"Selecting previously unselected package python3-venv."}

event: state
data: {"state":"ready","message":"hermes doctor: OK"}
```

### `GET /api/events` (SSE)
Aliran global: `service`, `approval`, `gateway`, `install`, `log`. Dipakai badge status di header dan notifikasi.

## Percakapan

### `POST /api/chat` (SSE)
```json
{
  "message": "Jelaskan RSC dengan analogi",
  "threadId": "t-1731000000",
  "session": null,
  "model": null,
  "provider": null,
  "toolsets": "web,terminal,skills",
  "skills": ["hermes-agent-dev"],
  "images": ["/mnt/arkax/inbox/screen.png"],
  "yolo": false,
  "safeMode": false,
  "maxTurns": 90
}
```
Perintah yang dihasilkan (argumen array, prompt lewat stdin):
```
hermes chat --query-file -
  [--continue "Arkax/<threadId>" --create-if-missing | --resume <session>]
  [--model …] [--provider …] [--toolsets …] [-s …] [--image …]
  [--yolo | --safe-mode] [--max-turns …] --pass-session-id --source arkaxhermes
```

Aliran:
```
event: chunk    data: {"text":"Tentu! Bayangkan …"}
event: tool     data: {"name":"terminal","detail":"apt list --installed"}
event: session  data: {"id":"ses_01J…","title":"Arkax/t-1731000000"}
event: done     data: {"exit":0,"tokens":412,"elapsedMs":1260}
event: error    data: {"message":"…","exit":1}
```
`POST /api/chat/stop` menghentikan proses aktif (`SIGTERM` → `SIGKILL` setelah 2 detik).

## Eksekusi & fitur

### `POST /api/exec`
```json
{"argv": ["hermes","doctor"], "stdin": null, "timeoutMs": 120000, "tty": false, "stream": false}
```
`argv` dijalankan **di dalam proot** (bukan shell Android). Bila `stream:true`, respons SSE `event: stdout|stderr|exit`. `tty:true` membungkus dengan `script -q -c … /dev/null` untuk `hermes --tui`. Untuk menjalankan perintah shell bebas, kirim `{"argv":["/bin/bash","-lc","<perintah>"]}` — ini dipakai layar Terminal.

```json
{"ok":true,"stdout":"Hermes Agent v0.23.1 …","stderr":"","exit":0,"elapsedMs":812}
```

### `POST /api/hermes/feature`
Satu endpoint untuk semua aksi `hermes_bridge.py`:
```json
{"action":"skills.list","payload":{}}
```
Aksi yang didukung (lihat `assets/runtime/hermes_bridge.py`):

| Grup | Aksi |
| --- | --- |
| Konfigurasi | `status`, `config.get`, `config.set`, `env.set`, `env.list`, `env.delete`, `providers.list`, `model.set`, `doctor`, `update` |
| Skills | `skills.list`, `skills.read`, `skills.write`, `skills.delete`, `skills.install`, `skills.nudges` |
| Memori | `memory.get`, `memory.set`, `memory.append`, `memory.providers`, `memory.clear` |
| Sesi | `sessions.list`, `sessions.search`, `sessions.read`, `sessions.delete`, `sessions.stats` |
| Cron | `cron.list`, `cron.create`, `cron.toggle`, `cron.run`, `cron.remove`, `cron.delivery` |
| Tools | `tools.list`, `tools.set`, `tools.backend` |
| MCP / plugin | `mcp.list`, `mcp.add`, `mcp.remove`, `plugins.list`, `plugins.install`, `plugins.remove` |
| Profil & bot | `profiles.list`, `profiles.create`, `profiles.use`, `bots.list`, `bots.set` |
| Otomasi lain | `hooks.list`, `hooks.set`, `trajectories.list`, `approvals.list`, `approvals.decide`, `context.list`, `context.add`, `batch.run` |
| Berkas | `files.list`, `files.read`, `files.write`, `files.delete`, `backup.create`, `backup.restore`, `export.chat` |

Respons umum:
```json
{"ok": true, "action":"skills.list", "data": […], "source":"filesystem", "warnings": []}
```
Bila aksi tidak tersedia pada rilis terpasang:
```json
{"ok": false, "action":"…", "error":"unsupported","fallback":{"argv":["hermes","skills"],"hint":"Buka Terminal"}}
```
UI menampilkan tombol **Jalankan di Terminal** — tidak pernah mengarang data.

### `GET|POST /api/files`
`GET /api/files?path=/root/.hermes/skills` → daftar. `POST` menerima `{path, content}` (base64 untuk biner), `DELETE` menerima `{path}`. Semua path dibatasi ke `/root/.hermes`, `/mnt/arkax`, `/opt/arkax`, dan `/opt/hermes-agent` (read-only untuk source).

### `GET /api/logs?lines=200`
Baris terakhir log gabungan: instalasi, `~/.hermes/logs/*`, gateway, service.

### `GET|POST /api/settings`
```json
{
  "theme": "system",          // light | dark | system
  "fontSize": 14,
  "haptics": true,
  "autoSave": true,
  "encryptLocal": true,
  "batteryExemptionAsked": false,
  "services": {"gateway": false, "cron": true, "dashboard": false},
  "chat": {"defaultProvider": "anthropic", "defaultModel": "", "toolsets": "web,terminal,skills", "yolo": false}
}
```
`POST` menyimpan sebagian (patch), menerapkan tema ke WebView, dan menyalakan/mematikan layanan yang berubah.

### `POST /api/service`
```json
{"name":"gateway|cron|dashboard|webhook","action":"start|stop|restart"}
```
Diteruskan ke `AgentService` → `/opt/arkax/services.sh`.

## JavascriptInterface (`window.ArkaxBridge`)

| Fungsi | Keterangan |
| --- | --- |
| `ready(): String` | JSON `{native:true, version, port, token, abi, sdk}` |
| `port(): int`, `token(): String`, `platform(): String` | info runtime |
| `setTheme(String)` | sinkronisasi status bar / `forceDark` |
| `haptic(String)` | `light`/`medium`/`heavy` saat token mengalir |
| `pickFile(String)` | SAF → salin ke `/mnt/arkax/inbox`, balasan lewat `window.__arkax.onFilePicked(json)` |
| `dictate()` | Android speech recognizer → `window.__arkax.onDictation(text)` |
| `shareText(String, String)` | `Intent.ACTION_SEND` untuk ekspor `.md`/`.json` |
| `copy(String)` | clipboard sistem |
| `openExternal(String)` | hanya `https://` |
| `requestPermissions(String)` | notifikasi, mic, pengecualian baterai |
| `startService(String)`, `stopService(String)` | shortcut ke `AgentService` |

## Mode demo (preview tanpa APK)

Bila `window.ArkaxBridge` tidak ada dan host bukan `127.0.0.1`, `index.html` memakai `DemoTransport`: data contoh persis seperti desain yang dilampirkan, chat disimulasikan token-demi-token, dan setiap tombol tetap memberi respons (toast "Mode demo — perintah akan dikirim ke proot"). Tidak ada permintaan jaringan eksternal, sehingga file ini bisa dibuka langsung di viewer workspace / browser offline.

## Kode error

| HTTP | `error` | Arti |
| --- | --- | --- |
| 400 | `bad_json`, `bad_path`, `bad_argv` | input tidak valid |
| 403 | `forbidden` | token/origin salah |
| 409 | `busy` | instalasi atau chat lain masih berjalan |
| 424 | `not_ready` | rootfs/Hermes belum siap |
| 500 | `exec_failed`, `bridge_failed` | lihat `detail` + `/api/logs` |
| 504 | `timeout` | proses melewati `timeoutMs` |
