# Ubuntu proot di dalam Arkaxhermes

## Mengapa proot, bukan Termux / chroot / VM

| Pendekatan | Kelebihan | Kenapa tidak dipilih |
| --- | --- | --- |
| Termux + paket APT Hermes | resmi, ringan | Dokumentasi resmi per **16 Nov 2026** memberi peringatan "Termux is currently broken"; paket terikat prefix `/data/data/com.termux/files/usr`, `sys.platform == "android"`, dan tidak menyertakan Electron/Chromium. Pengguna harus memasang aplikasi terpisah. |
| chroot | cepat | butuh root / `CAP_SYS_CHROOT`, tidak mungkin di Android stock |
| VM (QEMU/KVM) | isolasi kuat | butuh akses `/dev/kvm`, berat, baterai boros |
| **proot + Ubuntu glibc** | tanpa root, `sys.platform == "linux"`, apt penuh, Python/Node/toolchain standar, bisa dibundel | overhead syscall via `ptrace` (lihat batasan di bawah) |

Arkaxhermes memakai Ubuntu Base 24.04.5 LTS (`ubuntu-base-24.04.5-base-arm64.tar.gz`, SHA-256 `a91d5a93010193712d346d761372b7c9db6dfcf093893161c64ca107f05914f2`; amd64 `e77b6f10c2590cef872b33ee9f635a0e3fd1f57fb074c0e52b5c7f56147a0c86`, dari `SHA256SUMS` resmi cdimage.ubuntu.com) dan source Hermes `v0.23.1` yang dipin. Versi bisa diganti lewat `rootfs/manifest.json`.

## Isi rootfs

```
/                         Ubuntu Base 24.04.5 (glibc, apt, coreutils, bash)
/etc/resolv.conf          DNS (ditulis bootstrap.sh dari properti Android)
/etc/apt/sources.list.d/  mirror ports.ubuntu.com / archive.ubuntu.com per arsitektur
/opt/arkax/
  bootstrap.sh            setup user, DNS, apt, direktori, first-run marker
  install-hermes.sh       pasang Python 3.12+/Node 20+/git/uv/ffmpeg/ripgrep + source Hermes
  services.sh             start|stop|status gateway, cron ticker, dashboard, webhook
  doctor.sh               pemeriksaan lingkungan proot
  hermes_bridge.py        JSON-lines API untuk fitur tanpa CLI
  hermes-src.tar.gz       source Hermes (dibundel sebagai aset APK; TERLIHAT di sini
                          lewat bind filesDir/runtime → /opt/arkax, tidak diduplikasi)
  entrypoint.sh           env + exec perintah dari ProotRuntime
/opt/hermes-agent/        hasil ekstrak source (git clone bila tidak dibundel)
/usr/local/bin/hermes     wrapper → venv Python Hermes CLI
/root/.hermes/            config.yaml, .env, MEMORY.md, USER.md, skills/, sessions.db,
                          cron/jobs.json, plugins/, hooks/, profiles/, logs/, trajectories/
/mnt/arkax/               bind ke filesDir/shared milik Android
  inbox/                  lampiran dari SAF / kamera
  exports/                hasil ekspor & backup
  scripts/                skrip RPC / execute_code pengguna
```

## Perintah proot yang dipakai

```
<nativeLibraryDir>/libproot.so \
  -0 -r <filesDir>/rootfs/ubuntu -w /root \
  -b /proc -b /dev -b /sys \
  -b <filesDir>/shared:/mnt/arkax \
  -b <filesDir>/runtime:/opt/arkax \
  --link2symlink --kill-on-exit \
  /usr/bin/env -i \
    HOME=/root \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=xterm-256color \
    HERMES_HOME=/root/.hermes ARKAX_NATIVE=1 \
  /bin/bash /opt/arkax/entrypoint.sh '<argv…>'
```

Variabel untuk proses **proot itu sendiri** diisi di `ProcessBuilder.environment()` sebelum `start()`, bukan di `env -i` dalam rootfs:

- `LD_LIBRARY_PATH=<nativeLibraryDir>` → `libproot.so` Termux membutuhkan `libtalloc.so.2` dan `libandroid-shmem.so` yang dibundel di direktori yang sama.
- `PROOT_LOADER=<nativeLibraryDir>/libproot-loader.so` → loader yang disuntikkan ke proses yang di-`ptrace`.

Penjelasan flag:

- `-0` memalsukan uid/gid 0 supaya `apt`, `chown`, dan `pip` tidak menolak; **tidak** memberi hak kernel.
- `-r` rootfs, `-w` working directory, `-b` bind mount. `/proc`, `/dev`, `/sys` dibutuhkan Python/Node/SQLite; `/mnt/arkax` untuk bertukar berkas dengan Android.
- `--link2symlink` mengubah hardlink jadi symlink: filesystem Android (F2FS/ext4 userdata via sdcardfs) sering menolak hardlink yang dipakai `dpkg`.
- `--kill-on-exit` mencegah proses yatim saat aplikasi ditutup.
- `env -i` membersihkan variabel Android, lalu mengisi ulang yang perlu saja.
- `PROOT_LOADER` dan `LD_LIBRARY_PATH` hanya diisi bila `fetch-proot.sh` menemukan loader/dependency Termux; keduanya kini ikut dibundel secara otomatis.

## First-run

1. `RootfsInstaller` menggabungkan `ubuntu-rootfs.tar.gz.partNNN` → satu arsip di `filesDir`, mencocokkan SHA-256 dengan `assets/rootfs/rootfs.sha256`.
2. Parser TAR Kotlin menulis berkas (regular file, dir, symlink, hardlink, GNU longname `L`, PAX `x`), menjaga mode bit, menolak `..`.
3. `bootstrap.sh` → `apt-get update` (bila belum dipraset di host build) → `install-hermes.sh`.
4. `install-hermes.sh` lebih memilih source bundel daripada unduhan:
   ```bash
   tar -xzf /opt/arkax/hermes-src.tar.gz -C /opt/hermes-agent --strip-components=1
   uv sync --frozen   # atau python3 -m venv + pip install -e . bila uv tidak ada
   ln -sf /opt/hermes-agent/.venv/bin/hermes /usr/local/bin/hermes
   hermes --version && hermes doctor
   ```
   Jalur resmi `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` tersedia sebagai fallback lewat Pengaturan → Perbarui/Instal ulang.
5. `services.sh` menyalakan layanan yang ditandai autostart di `/api/settings`.
6. `hermes doctor` hasilnya ditampilkan di layar Instalasi; status `ready` disimpan di `SettingsStore`.

Langkah 1–2 (ekstraksi rootfs + source Hermes) **tidak membutuhkan internet**: keduanya dibundel. Langkah 3–4 memakai `apt-get` dan `uv/pip`; Ubuntu Base memang tidak menyertakan Python/Node, sehingga **first-run membutuhkan jaringan sekali**, kecuali paket dipanggang ke rootfs saat build di host Linux yang punya `proot` (`build-rootfs.sh` tanpa `--no-apt`) atau wheel Python ikut dibundel. Setelah itu environment dan `~/.hermes` persisten; jaringan berikutnya hanya untuk API model, Skills Hub, gateway, dan update.

## Update

| Komponen | Cara |
| --- | --- |
| Hermes CLI | Pengaturan → Perbarui Hermes (`hermes update`), atau ganti `--hermes-tag` lalu build APK baru |
| Paket Ubuntu | Terminal → `apt update && apt upgrade` di dalam proot |
| Seluruh rootfs | build ulang rootfs + APK; `~/.hermes` tidak ikut tertimpa (backup dulu lewat layar Backup) |
| proot | ganti `libproot.so` lewat APK baru |

## Batasan yang harus diketahui

**proot bukan sandbox keamanan.** Ia memakai `ptrace` untuk menerjemahkan path syscall. Tidak ada namespace PID/mount/user, tidak ada seccomp, tidak ada isolasi jaringan. Proses di dalam proot tetap berjalan sebagai UID aplikasi Android dan hanya bisa menjangkau apa yang bisa dijangkau aplikasi itu. Jangan jalankan kode yang tidak dipercaya tanpa approval gate Hermes.

| Batasan | Dampak | Mitigasi di Arkaxhermes |
| --- | --- | --- |
| Overhead `ptrace` | I/O dan `apt` lebih lambat (1,5–3×) | dependency dipasang saat build rootfs di host bila memungkinkan; progres ditampilkan |
| Tidak bisa `mount`, `chroot`, `ptrace` bertingkat, `iptables` | Docker daemon, KVM, sebagian sandbox tidak jalan | backend `ssh`/`modal`/`daytona`/`vercel_sandbox`; atau `docker` ke daemon remote |
| Filesystem Android tidak mendukung ownership/hardlink tertentu | `dpkg`/`chown` bisa gagal | `--link2symlink`, rootfs di `filesDir` (bukan `/sdcard`), fallback first-run |
| `/proc` milik kernel Android | beberapa metrik memakai RAM/CPU seluruh sistem | `SystemStats` membaca `/proc` host dan diberi label "perangkat" |
| Android membunuh proses background | gateway/cron bisa berhenti saat layar mati | `AgentService` foreground + wake lock + permintaan pengecualian baterai + status jujur di UI |
| Tidak ada TTY asli di Java `ProcessBuilder` | TUI butuh terminal | <a id="tty"></a>`script -q -c … /dev/null` di dalam rootfs; kontrol tombol panah diteruskan lewat stdin; rendering ANSI difilter ringan di UI |
| `seccomp`/`PR_SET_NO_NEW_PRIVS` pada Android 12+ | sebagian biner statis gagal | gunakan proot build Termux (sudah disesuaikan) atau NDK build |
| Python wheels khusus `android_24_arm64_v8a` tidak cocok | — | keuntungan pendekatan ini: wheel `manylinux` glibc standar yang dipakai Hermes desktop |
| Paket Termux resmi sedang bermasalah (Nov 2026) | — | Arkaxhermes tidak bergantung padanya |
| Chromium tidak dibundel | `browser_*` butuh browser | pasang `chromium` di rootfs atau pakai Browser Use lewat Nous Tool Gateway |
| Voice/wake-word native tidak ada | — | `JsBridge.dictate()` memakai speech recognizer Android, hasilnya jadi teks/lampiran |

### Distribusi

Google Play membatasi ukuran base APK/App Bundle dan punya kebijakan ketat untuk kode yang dieksekusi di luar bytecode yang ditinjau. Untuk distribusi resmi, siapkan **Play Asset Delivery** (asset pack `rootfs`) atau unduh rootfs terverifikasi saat first-run dengan SHA-256 yang tertanam di APK. Untuk sideload / F-Droid / distribusi langsung, APK split per ABI sudah cukup. Selalu simpan `rootfs.sha256` di dalam APK, bukan di server.

## Atribusi

- Ubuntu Base — Canonical, lisensi paket masing-masing: https://cdimage.ubuntu.com/ubuntu-base/
- proot — Termux / proot-me, GPL-2.0+: https://github.com/termux/proot
- libtalloc (Samba, LGPL) dan libandroid-shmem (Termux) — dependency `libproot.so`, diambil dari repositori paket Termux.
- Hermes Agent — Nous Research, MIT: https://github.com/NousResearch/hermes-agent
- Python, Node.js, uv, ripgrep, ffmpeg, dan paket APT lain sesuai lisensi masing-masing.

Arkaxhermes tidak berafiliasi dengan Nous Research, Canonical, atau Termux.
