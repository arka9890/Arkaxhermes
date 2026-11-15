# Arsitektur Arkaxhermes

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ANDROID APPLICATION (APK)                          │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ WebView  →  http://127.0.0.1:18789/  (assets/www/index.html)       │  │
│  │  • Chat · Provider · Workspace · Terminal · Pengaturan             │  │
│  │  • +20 layar fitur Hermes (drawer) · tema Terang/Gelap             │  │
│  │  • fetch('/api/…') + SSE streaming + JsBridge (file, mic, haptic)  │  │
│  └───────────┬──────────────────────────────────┬─────────────────────┘  │
│              │ HTTP lokal (token per proses)     │ JavascriptInterface   │
│  ┌───────────▼──────────────────────────────────▼─────────────────────┐  │
│  │ ArkaxHttpServer (ServerSocket, 127.0.0.1 only)                     │  │
│  │  /api/status /api/install /api/install/stream /api/chat (SSE)      │  │
│  │  /api/exec /api/hermes/* /api/files /api/settings /api/events      │  │
│  └───────────┬────────────────────────────────────────────────────────┘  │
│              │                                                            │
│  ┌───────────▼───────────────┐   ┌────────────────────────────────────┐  │
│  │ HermesRuntime              │   │ RootfsInstaller / AssetExtractor   │  │
│  │  streamChat, exec, feature │   │  TAR+GZIP parser Kotlin, SHA-256   │  │
│  │  services, doctor, update  │   │  partNNN → filesDir/rootfs/ubuntu  │  │
│  └───────────┬───────────────┘   └──────────────────┬─────────────────┘  │
│              │                                      │                     │
│  ┌───────────▼──────────────────────────────────────▼─────────────────┐  │
│  │ ProotRuntime                                                        │  │
│  │  nativeLibraryDir/libproot.so -0 -r <rootfs> -w /root               │  │
│  │  -b /proc -b /dev -b /sys -b <shared>:/mnt/arkax --link2symlink     │  │
│  │  /usr/bin/env -i … /bin/bash -lc "<command>"                        │  │
│  └───────────┬────────────────────────────────────────────────────────┘  │
│              │ (tanpa root, tanpa namespace kernel)                       │
│  ┌───────────▼────────────────────────────────────────────────────────┐  │
│  │ UBUNTU 24.04 ROOTFS (dibundel)                                     │  │
│  │  /opt/arkax/  bootstrap.sh · install-hermes.sh · services.sh        │  │
│  │               hermes_bridge.py · doctor.sh · hermes-src.tar.gz      │  │
│  │  /opt/hermes-agent/   source NousResearch/hermes-agent v0.23.1     │  │
│  │  /usr/local/bin/hermes                                              │  │
│  │  /root/.hermes/  config.yaml · .env · MEMORY.md · USER.md           │  │
│  │                  skills/ · sessions.db (FTS5) · cron/jobs.json      │  │
│  │                  plugins/ · hooks/ · profiles/ · trajectories/      │  │
│  │  /mnt/arkax/  inbox/ · exports/ · scripts/  ← jembatan ke Android   │  │
│  └───────────┬────────────────────────────────────────────────────────┘  │
│              │                                                            │
│  ┌───────────▼────────────────────┐  ┌───────────────────────────────┐  │
│  │ AgentService (foreground)      │  │ LLM API / Nous Portal / Ollama │  │
│  │  gateway · cron ticker ·       ├─►│  · MCP · SSH/Modal/Daytona     │  │
│  │  dashboard · webhook · wake lock│  │  · Telegram/Discord/Slack …    │  │
│  └────────────────────────────────┘  └───────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

## Keputusan desain

**1. WebView + server HTTP lokal, bukan `file://` + JavascriptInterface saja.**
Halaman dimuat dari `http://127.0.0.1:18789/`, sehingga `fetch`, SSE (`ReadableStream`), dan `EventSource` bekerja dengan origin normal. Semua panggilan UI punya satu jalur (`/api/...`) yang juga bisa dipakai perangkat lain di sesi debug. `cleartextTrafficPermitted` hanya untuk `127.0.0.1`/`localhost`. `JavascriptInterface` dipakai untuk kemampuan Android murni: pilih berkas (SAF), dikte, haptic, bagikan teks, buka URL eksternal, izin notifikasi.

**2. proot sebagai native library.** Android 10+ menolak `execve()` pada berkas di direktori data aplikasi yang writable. `libproot.so` ditaruh di `jniLibs/<abi>/`, diekstrak ke `nativeLibraryDir` yang tidak writable, dan dieksekusi dari sana. Skrip shell di `filesDir` tidak dieksekusi langsung melainkan dipanggil lewat `/bin/sh` di dalam rootfs.

**3. Rootfs & source dibundel; dependency dipasang sekali.** `RootfsInstaller` punya parser TAR/GZIP sendiri (ustar + GNU longname + PAX + symlink + hardlink + mode bit) karena `tar` tidak dijamin ada di Android dan proot belum bisa dipakai sebelum rootfs ada. Arsip dipecah 24 MB; checksum gabungan diverifikasi terhadap `assets/rootfs/rootfs.sha256`. Source Hermes juga dibundel, tetapi Ubuntu Base tidak membawa Python/Node: `bootstrap.sh` memasangnya lewat `apt-get` + `uv/pip` pada first-run (jaringan sekali), atau paket itu dipanggang ke rootfs oleh `build-rootfs.sh` di host yang punya proot.

**4. Hermes tidak di-fork.** Semua kemampuan dipanggil lewat CLI asli (`hermes chat`, `hermes cron`, `hermes gateway`, `hermes tools`, …) atau lewat berkas konfigurasi asli di `~/.hermes`. `hermes_bridge.py` hanya menyajikan aksi berstruktur JSON untuk hal-hal yang tidak punya subcommand JSON: daftar/edit skills, memory, pencarian FTS5, cron jobs.json, MCP, profil, approval, backup. Bila sebuah CLI tidak dikenali, bridge mengembalikan `{ok:false, fallback:"cli"}` dan UI langsung membuka Terminal — tidak ada hasil palsu.

**5. Prompt lewat stdin, bukan interpolasi shell.** `HermesRuntime.streamChat` memakai `hermes chat --query-file -` dan menulis prompt ke `Process.outputStream`. Argumen lain dikirim sebagai `List<String>` ke `ProcessBuilder`, jadi tanda kutip, backtick, dan `$(...)` dari pengguna tidak pernah diinterpretasi shell.

**6. Sesi kontinu.** Setiap thread UI dipetakan ke judul sesi Hermes (`--continue "Arkax/<threadId>" --create-if-missing`). `--pass-session-id` dipakai agar ID sesi bisa ditampilkan dan dipakai `hermes_bridge.py` untuk membuka riwayat. `--source arkaxhermes` menandai sesi agar mudah difilter.

**7. Kunci tidak lewat WebView.** `KeyVault` (Android Keystore AES-GCM) menyimpan ciphertext di SharedPreferences; dekripsi terjadi di Kotlin lalu ditulis ke `~/.hermes/.env` (mode `0600`) oleh bridge. Form Provider hanya mengirim `{provider, keyName, value}` ke `/api/hermes/env` dan tidak menyimpan nilainya di `localStorage`.

**8. Proses panjang = foreground service.** Gateway, cron ticker, dashboard, dan webhook dijalankan `AgentService` dengan notifikasi ongoing, `PARTIAL_WAKE_LOCK`, dan opsi pengecualian optimasi baterai. `ServiceState` dibagikan ke `/api/status` dan `/api/events`. Android tetap dapat membunuhnya; UI menampilkan status jujur, bukan "online" palsu.

## Alur data: satu pesan chat

```
User mengetik → POST /api/chat {message, threadId, model, toolsets, skills}
  → HermesRuntime.streamChat()
  → ProcessBuilder([libproot.so, …, /bin/bash, -lc, "hermes chat --query-file - …"])
  → stdin ← prompt
  → stdout baris-demi-baris → SSE: {type:"chunk"|"tool"|"session"|"done"|"error"}
  → WebView ReadableStream → render bubble bertahap + panel aktivitas alat
  → sesi tersimpan otomatis di ~/.hermes/sessions.db oleh Hermes
```

## Alur data: fitur tanpa CLI (mis. edit MEMORY.md)

```
Layar Memori → POST /api/hermes/feature {action:"memory.set", payload:{…}}
  → proot: python3 /opt/arkax/hermes_bridge.py memory.set '<json>'
  → path discovery ~/.hermes → tulis atomik (tmp + os.replace) + backup .bak
  → JSON {ok:true, data:{…}} → UI refresh
```

## Threading & lifecycle

- `ArkaxHttpServer`: `ServerSocket` + `Executors.newCachedThreadPool()`; koneksi SSE ditandai dan ikut ditutup saat `stop()`.
- `Process` proot: dibuat per permintaan untuk `chat`/`exec`; proses layanan panjang disimpan dalam `ServiceState.processes` dan di-`destroy()` saat stop.
- `EventBus` (`CopyOnWriteArrayList`) menyalurkan progres instalasi, log, approval, dan status layanan ke semua klien SSE.
- `MainActivity.onDestroy` → `server.stop()`; `AgentService` tetap hidup bila layanan aktif.
- `BootReceiver` menyalakan kembali layanan yang ditandai "autostart" di `SettingsStore`.

## Permukaan keamanan

| Ancaman | Mitigasi |
| --- | --- |
| Aplikasi lain memanggil server jembatan | bind `127.0.0.1`, token acak per proses di header `X-Arkax-Token`, cek `Origin`/`Referer`, port ephemeral dicatat di log |
| Halaman/web jahat di WebView | `WebViewClient` memblokir navigasi keluar, `Intent` hanya untuk skema `https://`, `setAllowUniversalAccessFromFileURLs(false)` |
| Path traversal saat ekstrak TAR / baca berkas | normalisasi + `startsWith(root)` di `RootfsInstaller` dan `hermes_bridge.py` |
| Kunci API bocor | Keystore + `.env` 0600 + tidak pernah dikirim balik ke UI (endpoint `env.list` hanya mengembalikan nama variabel + `••••`) |
| Prompt injection → eksekusi perintah | approval gate Hermes tetap aktif; `--yolo` hanya lewat toggle eksplisit; `--safe-mode` tersedia satu ketukan |
| Arsip rootfs dimodifikasi | SHA-256 wajib; tidak ada bypass |
| Proses liar | `--kill-on-exit`, timeout per `exec`, tombol Stop mengirim `SIGTERM` lalu `SIGKILL` |

Batasan inheren proot (bukan sandbox keamanan) dibahas di [docs/PROOTFS.md](docs/PROOTFS.md).
