#!/usr/bin/env bash
# Watch one job log. Output changes are progress; two quiet intervals are a stall.
#   bash watch.sh --log PATH --expect-secs N [--metric-script PATH]
# The job writes its numeric exit code atomically to PATH.exit.
set -uo pipefail

LOG= EXPECT= METRIC= STALL= MAX=
NOISE_RE='^[[:space:]]*$|[Ww]arning'

while [ $# -gt 0 ]; do
  case "$1" in
    --log) LOG=$2; shift 2 ;;
    --expect-secs) EXPECT=$2; shift 2 ;;
    --metric-script) METRIC=$2; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$LOG" ] || [ -z "$EXPECT" ] || ! [[ "$EXPECT" =~ ^[0-9]+$ ]]; then
  echo "need --log and --expect-secs" >&2
  exit 2
fi

INTERVAL=${HB_INTERVAL_SECS:-$(( EXPECT / 360 ))}
[ -z "${HB_INTERVAL_SECS:-}" ] && {
  [ "$INTERVAL" -lt 10 ] && INTERVAL=10
  [ "$INTERVAL" -gt 30 ] && INTERVAL=30
  INTERVAL=$(( INTERVAL * 60 ))
}
[ -z "$STALL" ] && STALL=$(( INTERVAL * 2 ))
[ -z "$MAX" ] && MAX=$(( EXPECT * 2 ))

ts() { date -u +%Y-%m-%dT%H:%MZ; }
last_line() {
  tail -n 400 "$LOG" 2>/dev/null | grep -a -v -E "$NOISE_RE" | tail -n 1 | cut -c1-160 || true
}
read_metric() {
  [ -z "$METRIC" ] && return
  [ -x "$METRIC" ] || { printf unavailable; return; }
  local value
  value=$("$METRIC" 2>/dev/null) || { printf unavailable; return; }
  printf '%s' "$value" | tail -n 1 | cut -c1-160
}

echo "WATCH $(ts) interval=${INTERVAL}s stall=${STALL}s"
start=$(date +%s)
prev_line= prev_metric=
quiet_from=$start
missing=0

while :; do
  now=$(date +%s)
  [ $(( now - start )) -ge "$MAX" ] &&
    { echo "WATCH_TIMEOUT $(ts)"; exit 2; }

  if [ ! -r "$LOG" ]; then
    missing=$(( missing + 1 ))
    [ "$missing" -ge 2 ] &&
      { echo "DEAD $(ts) unreadable $LOG"; exit 3; }
    echo "HB $(ts) alive quiet=0s | log not created"
    sleep "$INTERVAL"
    continue
  fi
  missing=0

  if [ -r "$LOG.exit" ]; then
    code=$(tr -d '[:space:]' < "$LOG.exit")
    if [ "$code" = 0 ]; then
      echo "RUN_ENDED $(ts) | $(last_line)"
      exit 0
    elif [[ "$code" =~ ^[0-9]+$ ]]; then
      echo "RUN_ERROR $(ts) exit=$code | $(last_line)"
      exit 1
    fi
  fi

  line=$(last_line)
  metric=$(read_metric)
  if { [ -n "$line" ] && [ "$line" != "$prev_line" ]; } ||
     { [ -n "$metric" ] && [ "$metric" != "unavailable" ] && [ "$metric" != "$prev_metric" ]; }; then
    prev_line=$line; prev_metric=$metric
    quiet_from=$now
    echo "HB $(ts) alive${metric:+ metric=$metric} | $line"
  else
    quiet=$(( now - quiet_from ))
    if [ "$quiet" -ge "$STALL" ]; then
      echo "STALL $(ts) quiet=${quiet}s${metric:+ metric=$metric} | $line"
    else
      echo "HB $(ts) alive quiet=${quiet}s${metric:+ metric=$metric} | $line"
    fi
  fi
  sleep "$INTERVAL"
done
