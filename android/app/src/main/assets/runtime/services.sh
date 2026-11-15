#!/bin/bash
# Layanan panjang Hermes di dalam proot. Dipanggil AgentService.kt.
# usage: services.sh start|stop|restart|status <gateway|cron|dashboard|webhook|all>
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/root/.hermes}"
RUN="$HERMES_HOME/run"
LOG="$HERMES_HOME/logs"
mkdir -p "$RUN" "$LOG"

ACTION="${1:-status}"
NAME="${2:-all}"

# Peta perintah. Beberapa subcommand berbeda antar rilis Hermes; cek dulu
# dengan `hermes <sub> --help` lalu fallback ke perintah yang tersedia.
cmd_for() {
  case "$1" in
    gateway)
      echo "hermes gateway run" ;;
    cron)
      if hermes cron ticker --help >/dev/null 2>&1; then
        echo "hermes cron ticker"
      else
        # Scheduler cron di Hermes dijalankan oleh proses gateway.
        echo "hermes gateway run"
      fi ;;
    dashboard)
      echo "hermes dashboard" ;;
    webhook)
      echo "hermes gateway run" ;;
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
  ARKAX_SERVICE="$n" nohup setsid /bin/bash -lc "$cmd" >> "$LOG/$n.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$(pid_file "$n")"
  sleep 0.4
  if kill -0 "$pid" 2>/dev/null; then echo "started:$n:$pid"; else echo "failed:$n"; return 1; fi
}

stop_one() {
  local n="$1" f pid
  f="$(pid_file "$n")"
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
  local n="$1"
  if is_running "$n"; then
    echo "running:$n:$(cat "$(pid_file "$n")")"
  else
    echo "stopped:$n"
  fi
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
