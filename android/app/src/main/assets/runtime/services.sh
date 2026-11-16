#!/bin/bash
# Layanan panjang Hermes di dalam proot. Dipanggil AgentService.kt.
# usage: services.sh start|stop|restart|status <gateway|cron|dashboard|webhook|all>
#
# Perintah diverifikasi terhadap `hermes --help` v0.23.1:
#   gateway run / gateway status / cron status / cron tick
#   serve --status / serve --stop / webhook list
# Tidak ada `hermes dashboard serve`, tidak ada daemon webhook terpisah, dan
# tidak ada `cron ticker`; scheduler 60 detik dijalankan loop di bawah.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
RUN="$HERMES_HOME/run"
LOG="$HERMES_HOME/logs"
mkdir -p "$RUN" "$LOG"

ACTION="${1:-status}"
NAME="${2:-all}"

cmd_for() {
  case "$1" in
    gateway)
      echo "ARKAX_SERVICE=gateway /usr/local/bin/hermes gateway run --replace" ;;
    cron)
      # `hermes cron tick` melakukan SATU tick; loop 60 detik meniru scheduler
      # bawaan tanpa bergantung pada systemd/user-service Android.
      echo "ARKAX_SERVICE=cron /bin/bash -c 'while true; do /usr/local/bin/hermes cron tick --accept-hooks >> \"$LOG/cron-tick.log\" 2>&1; sleep 60; done'" ;;
    dashboard)
      # `serve` = backend headless JSON-RPC/WS untuk Desktop/TUI; `dashboard`
      # polos mencoba membuka browser, jadi tidak dipakai di Android.
      echo "ARKAX_SERVICE=dashboard /usr/local/bin/hermes serve --host 127.0.0.1 --port 9119 --skip-build" ;;
    webhook)
      # Webhook subscription disajikan proses gateway; tidak ada daemon terpisah.
      echo "ARKAX_SERVICE=webhook /usr/local/bin/hermes gateway run --replace" ;;
    *) echo "" ;;
  esac
}

status_cmd() {
  case "$1" in
    gateway)  echo "/usr/local/bin/hermes gateway status" ;;
    cron)     echo "/usr/local/bin/hermes cron status" ;;
    dashboard) echo "/usr/local/bin/hermes serve --status" ;;
    webhook)  echo "/usr/local/bin/hermes webhook list || true" ;;
    *) echo "" ;;
  esac
}

pid_file() { echo "$RUN/$1.pid"; }
is_running() {
  local f; f="$(pid_file "$1")"
  [[ -f "$f" ]] && kill -0 "$(cat "$f")" 2>/dev/null
}

start_one() {
  local n="$1" cmd
  cmd="$(cmd_for "$n")"
  [[ -n "$cmd" ]] || { echo "unknown:$n"; return 1; }
  if is_running "$n"; then echo "already:$n:$(cat "$(pid_file "$n")")"; return 0; fi
  # `nohup` + setsid agar proses tidak mati saat parent (proot) selesai.
  nohup setsid /bin/bash -lc "$cmd" >> "$LOG/$n.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$(pid_file "$n")"
  sleep 0.5
  if kill -0 "$pid" 2>/dev/null; then echo "started:$n:$pid"; else echo "failed:$n"; return 1; fi
}

stop_one() {
  local n="$1" f pid
  f="$(pid_file "$n")"
  if [[ "$n" == "dashboard" ]]; then
    /usr/local/bin/hermes serve --stop >/dev/null 2>&1 || true
  fi
  if [[ ! -f "$f" ]]; then echo "stopped:$n"; return 0; fi
  pid="$(cat "$f")"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.3
  done
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$f"
  echo "stopped:$n"
}

status_one() {
  local n="$1" cmd out
  cmd="$(status_cmd "$n")"
  if [[ -z "$cmd" ]]; then echo "unknown:$n"; return 1; fi
  out="$(/bin/bash -lc "$cmd" 2>&1 || true)"
  if is_running "$n"; then
    echo "running:$n:$(cat "$(pid_file "$n")")"
  else
    echo "stopped:$n"
  fi
  printf '%s\n' "$out" | sed "s/^/[$n] /"
}

names=(gateway cron dashboard webhook)
[[ "$NAME" != "all" ]] && names=("$NAME")

case "$ACTION" in
  start)   for n in "${names[@]}"; do start_one "$n"; done ;;
  stop)    for n in "${names[@]}"; do stop_one "$n"; done ;;
  restart) for n in "${names[@]}"; do stop_one "$n" >/dev/null; start_one "$n"; done ;;
  status)  for n in "${names[@]}"; do status_one "$n"; done ;;
  *) echo "usage: $0 start|stop|restart|status <gateway|cron|dashboard|webhook|all>"; exit 2 ;;
esac
