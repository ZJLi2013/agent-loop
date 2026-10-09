#!/usr/bin/env bash
# Pull new heartbeat lines with short SSH connections.
#   bash poll.sh --ssh NODE --hb /remote/job.log.hb --expect-secs N
set -uo pipefail

NODE= HB= EXPECT=

while [ $# -gt 0 ]; do
  case "$1" in
    --ssh) NODE=$2; shift 2 ;;
    --hb) HB=$2; shift 2 ;;
    --expect-secs) EXPECT=$2; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$NODE" ] || [ -z "$HB" ] || [ -z "$EXPECT" ] || ! [[ "$EXPECT" =~ ^[0-9]+$ ]]; then
  echo "need --ssh, --hb, and --expect-secs" >&2
  exit 2
fi

INTERVAL=${HB_INTERVAL_SECS:-$(( EXPECT / 360 ))}
[ -z "${HB_INTERVAL_SECS:-}" ] && {
  [ "$INTERVAL" -lt 10 ] && INTERVAL=10
  [ "$INTERVAL" -gt 30 ] && INTERVAL=30
  INTERVAL=$(( INTERVAL * 60 ))
}

ts() { date -u +%Y-%m-%dT%H:%MZ; }
next=1
misses=0
hb_q=$(printf '%q' "$HB")

while :; do
  reason=
  if ! chunk=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$NODE" \
      "if [ -r $hb_q ]; then tail -n +$next -- $hb_q; else echo WAITING; fi" 2>&1); then
    reason="ssh failed"
  elif [ "$chunk" = "WAITING" ]; then
    reason="heartbeat log missing"
  elif [ -z "$chunk" ]; then
    reason="watcher silent"
  fi

  if [ -n "$reason" ]; then
    misses=$(( misses + 1 ))
    [ "$misses" -ge 2 ] && { echo "DEAD $(ts) $reason"; exit 3; }
    sleep "$INTERVAL"
    continue
  fi
  misses=0

  added=$(printf '%s\n' "$chunk" | wc -l)
  next=$(( next + added ))
  printf '%s\n' "$chunk"
  while IFS= read -r line; do
    case "$line" in
      RUN_ENDED*) exit 0 ;;
      RUN_ERROR*) exit 1 ;;
      WATCH_TIMEOUT*) exit 2 ;;
      DEAD*) exit 3 ;;
    esac
  done <<< "$chunk"
  sleep "$INTERVAL"
done
