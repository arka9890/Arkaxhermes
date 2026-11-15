# Runtime aset (dijalankan di dalam Ubuntu proot)

Berkas di folder ini disalin `ArkaxHttpServer`/`ProotRuntime` ke `filesDir/runtime` lalu di-bind ke `/opt/arkax` di dalam rootfs. Semua skrip juga ikut dibundel ke `/opt/arkax` oleh `scripts/build-rootfs.sh`.

| Berkas | Dipanggil oleh | Fungsi |
| --- | --- | --- |
| `bootstrap.sh` | `RootfsInstaller` saat first run | DNS, apt, direktori `~/.hermes`, merge `secrets.env`, doctor |
| `install-hermes.sh` | `bootstrap.sh`, tombol "Instal ulang" | ekstrak source bundel / clone, `uv sync` atau venv+pip, wrapper `/usr/local/bin/hermes` |
| `entrypoint.sh` | `ProotRuntime` untuk setiap perintah | env bersih + `exec "$@"` |
| `services.sh` | `AgentService` | start/stop/restart/status gateway, cron, dashboard, webhook |
| `doctor.sh` | `/api/hermes/feature {action:"doctor"}` | pemeriksaan Python/Node/hermes/DNS/disk |
| `hermes_bridge.py` | `/api/hermes/feature` | JSON API untuk skills, memory, sesi FTS5, cron, MCP, tools, plugin, profil, approval, backup |

`hermes-src.tar.gz` (source Hermes Agent yang dipin) dibuat oleh `scripts/fetch-hermes-src.sh` dan **tidak disimpan di git**.

Kontrak output skrip: baris `ARKAX:step:<nama>:<persen>:<pesan>` → SSE `progress`; `ARKAX:log:<teks>` → SSE `log`. Lihat [docs/BRIDGE_API.md](../../../../../docs/BRIDGE_API.md).

Jangan pernah mencetak isi `~/.hermes/.env` ke log: berisi kunci API.
