#!/usr/bin/env bash
# cleanup-storage.sh — Clean up storage on a remote GPU node
# Usage: bash cleanup-storage.sh <hostname> [user] [--dry-run]
# Executes tiered cleanup: cold (3d) → warm (7d) → pip cache

set -o pipefail

NODE="${1:?Usage: cleanup-storage.sh <hostname> [user] [--dry-run]}"
USER="${2:-zhengjli}"
DRY_RUN="${3:-}"

echo "=== Storage Cleanup: $NODE ==="
[ "$DRY_RUN" = "--dry-run" ] && echo "*** DRY RUN — no files will be deleted ***"

ssh -A -o ConnectTimeout=10 "${USER}@${NODE}" bash -s -- "$DRY_RUN" <<'CLEANUP_EOF'
DRY_RUN="$1"
WORKDIR="/tmp/overnight-tests"
CACHE_ROOT="/data/cache"
[ ! -d "$CACHE_ROOT" ] && CACHE_ROOT="/tmp/cache"

# Hot models — NEVER delete
HOT_MODELS="sam2|sam3d|dinov2|siglip|wan2.1|da3-depth"

echo "=== Before Cleanup ==="
df -h /tmp /data /home 2>/dev/null || df -h /

echo ""
echo "--- Cold Tier: build artifacts older than 3 days ---"
if [ -d "$WORKDIR" ]; then
  find "$WORKDIR" -maxdepth 2 -name ".venv" -mtime +3 2>/dev/null | while read d; do
    echo "  COLD: $d ($(du -sh "$d" 2>/dev/null | cut -f1))"
    [ "$DRY_RUN" != "--dry-run" ] && rm -rf "$d"
  done
  find "$WORKDIR" -maxdepth 2 -name "build" -mtime +3 2>/dev/null | while read d; do
    echo "  COLD: $d ($(du -sh "$d" 2>/dev/null | cut -f1))"
    [ "$DRY_RUN" != "--dry-run" ] && rm -rf "$d"
  done
  find "$WORKDIR" -maxdepth 3 -name "__pycache__" 2>/dev/null | while read d; do
    [ "$DRY_RUN" != "--dry-run" ] && rm -rf "$d"
  done
  echo "  Cleaned __pycache__ dirs"
fi

echo ""
echo "--- Warm Tier: repo-specific checkpoints older than 7 days ---"
if [ -d "$CACHE_ROOT/models" ]; then
  find "$CACHE_ROOT/models" -maxdepth 1 -mindepth 1 -atime +7 2>/dev/null | while read d; do
    basename=$(basename "$d")
    if echo "$basename" | grep -qEi "^($HOT_MODELS)$"; then
      echo "  KEEP (hot): $d"
    else
      echo "  WARM: $d ($(du -sh "$d" 2>/dev/null | cut -f1))"
      [ "$DRY_RUN" != "--dry-run" ] && rm -rf "$d"
    fi
  done
fi

echo ""
echo "--- Pip Cache ---"
pip cache info 2>/dev/null | head -3
[ "$DRY_RUN" != "--dry-run" ] && pip cache purge 2>/dev/null && echo "  Pip cache purged"

echo ""
echo "--- Docker Cleanup ---"
if command -v docker &>/dev/null; then
  echo "  Before:"
  docker system df 2>/dev/null

  # Step 1: container prune — 先清理停止的容器（最安全、最明确）
  STOPPED=$(docker ps -a --filter "status=exited" -q 2>/dev/null | wc -l)
  echo "  Stopped containers: $STOPPED"
  if [ "$DRY_RUN" != "--dry-run" ]; then
    docker container prune -f 2>/dev/null && echo "  Step 1: stopped containers pruned"
  else
    echo "  DRY RUN: would run 'docker container prune -f'"
  fi

  # Step 2: kill zombie containers older than 90 days (still running but forgotten)
  echo ""
  echo "  Zombie containers (created >90 days ago, still running):"
  CUTOFF=$(date -d "90 days ago" +%s 2>/dev/null || date -v-90d +%s 2>/dev/null)
  docker ps --format '{{.ID}} {{.CreatedAt}} {{.Image}} {{.Status}}' 2>/dev/null | while read CID CREATED_DATE CREATED_TIME TZ IMAGE STATUS_REST; do
    CREATED_TS=$(date -d "${CREATED_DATE} ${CREATED_TIME}" +%s 2>/dev/null || echo 0)
    if [ "$CREATED_TS" -gt 0 ] && [ "$CREATED_TS" -lt "${CUTOFF:-0}" ]; then
      AGE_DAYS=$(( ($(date +%s) - CREATED_TS) / 86400 ))
      echo "    ZOMBIE (${AGE_DAYS}d): $CID $IMAGE"
      if [ "$DRY_RUN" != "--dry-run" ]; then
        docker stop "$CID" 2>/dev/null && docker rm "$CID" 2>/dev/null && echo "      → killed & removed"
      else
        echo "      DRY RUN: would stop+rm"
      fi
    fi
  done

  # Step 3: dangling images + build cache
  if [ "$DRY_RUN" != "--dry-run" ]; then
    docker image prune -f 2>/dev/null && echo "  Step 3: dangling images pruned"
    docker builder prune -f 2>/dev/null && echo "  Step 3: build cache pruned"
  fi

  echo "  After:"
  docker system df 2>/dev/null
else
  echo "  Docker: not available"
fi

echo ""
echo "=== After Cleanup ==="
df -h /tmp /data /home 2>/dev/null || df -h /
echo "=== Done ==="
CLEANUP_EOF
