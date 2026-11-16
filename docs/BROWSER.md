# Browser bawaan Arkaxhermes

Arkaxhermes memakai [`vercel-labs/agent-browser`](https://github.com/vercel-labs/agent-browser) sebagai browser yang benar-benar dipakai Hermes Agent, lalu menampilkannya di **tab Browser** aplikasi.

Ini bukan WebView kedua yang hanya membuka URL. Alurnya:

```
Tab Browser (WebView UI)
   ├── HTTP /api/browser/*  → ArkaxHttpServer → BrowserRuntime → agent-browser CLI
   └── WebSocket ws://127.0.0.1:9223 → daemon CDP agent-browser → frame JPEG + input
                                      │
                                      └── Chrome for Testing headless-shell
```

## Versi yang dipin

| Komponen | Versi | Lisensi / catatan |
| --- | --- | --- |
| `agent-browser` | `v0.43.0` (rilis 12 Nov 2026) | Apache-2.0, binary `linux-arm64` diverifikasi SHA-256 |
| Chrome for Testing headless-shell | `157.0.8103.78`, revision `1717349` | platform `linux-arm64`, ±128 MB |
| Session | `arkaxhermes` | tetap, supaya UI dan CLI memakai browser yang sama |
| Stream | port `9223` | WebSocket frame JPEG, ack pacing, `maxFps=8` |
| Dashboard | port `4848` | observability bawaan `agent-browser dashboard start` |

## Berkas & path

| Path | Isi |
| --- | --- |
| `android/app/src/main/jniLibs/arm64-v8a/libagent-browser.so` | CLI Rust; dieksekusi dari `nativeLibraryDir` |
| `browser_pack/src/main/assets/chrome-headless-shell.zip` | dibuat `fetch-agent-browser.sh --stage-assets` saat build APK |
| `filesDir/browser/chrome/` | hasil ekstraksi ZIP oleh `BrowserRuntime.kt` |
| `/opt/arkax/native/libagent-browser.so` | bind `nativeLibraryDir` di dalam proot |
| `/mnt/arkax/browser/chrome-wrapper.sh` | wrapper Chrome dengan `--no-sandbox --disable-dev-shm-usage --disable-gpu` |
| `/usr/local/bin/agent-browser` | wrapper final: `--json --session arkaxhermes --executable-path … --args …` |
| `/root/.agent-browser/config.json` | port stream/dashboard dan engine default |
| `/root/.hermes/skills/agent-browser/SKILL.md` | memberi tahu Hermes untuk memakai CLI ini |

## Menjalankan

Otomatis saat first-run lewat `bootstrap.sh → browser-bootstrap.sh`, dan layanan `browser` bisa dinyalakan lewat `AgentService`. Dari tab Browser:

- **Start** → `POST /api/browser/start` → `dashboard start --port 4848` + `open about:blank`.
- **Hubungkan** → membuat `WebSocket` ke `ws://127.0.0.1:9223/?pacing=ack&maxFps=8`.
- **Buka / Back / Forward / Reload** → `POST /api/browser/command` dengan argv `agent-browser`.
- **Snapshot / Screenshot / Tabs / Status** → perintah CLI yang sama.
- **Dashboard** → `ArkaxBridge.openBrowserDashboard()` membuka `http://127.0.0.1:4848`.

Input pengguna pada gambar viewport dikirim balik sebagai `input_mouse`, `input_keyboard`, atau `input_touch` sesuai [protokol streaming agent-browser](https://agent-browser.dev/streaming). Jadi pengguna bisa "pair browsing" bersama agent.

## Build

```bash
./scripts/fetch-agent-browser.sh            # unduh CLI + Chrome ZIP ke dist/
./scripts/make-assets.sh                    # termasuk --binaries-only
./scripts/build-apk.sh debug                # otomatis --stage-assets lalu Gradle
```

Chrome ZIP **tidak disimpan di Git** karena ukurannya ±128 MB dan akan melewati batas snapshot repo. `build-apk.sh` menyalinnya ke modul `browser_pack` (`com.android.asset-pack`, `deliveryType = "install-time"`) sebelum Gradle, sehingga APK/AAB final tetap membawa browser secara offline.

## Batasan jujur

- Chrome berjalan headless di proot tanpa root; `--no-sandbox`, tanpa GPU, dan `/dev/shm` dimatikan. Ekstensi Chrome, WebGPU penuh, dan profil persistent tertentu tidak dijamin.
- Dashboard Next.js dibuka di browser sistem karena tidak ramah di-iframe; **tab Browser di aplikasi** tetap menampilkan viewport live secara native.
- Port `9223`/`4848` hanya loopback. WebView diizinkan mengaksesnya lewat `network_security_config.xml`.
- Jika asset pack belum distagel, tab Browser menampilkan status jelas dan `doctor.sh` menandai Chrome belum siap — bukan screenshot palsu.
- APK belum dirakit di sandbox ini; file binary sudah ada di workspace, tetapi verifikasi runtime Chrome arm64 harus dilakukan di perangkat Android / emulator.
