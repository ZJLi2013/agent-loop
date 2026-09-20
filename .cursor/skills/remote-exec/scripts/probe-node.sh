#!/usr/bin/env bash
# probe-node.sh — Probe a single GPU node for resources
# Usage: bash probe-node.sh <hostname> [user]
# Output: structured text (parseable by agent)

set -o pipefail

NODE="${1:?Usage: probe-node.sh <hostname> [user]}"
USER="${2:-zhengjli}"

echo "=== Probing $NODE ==="

ssh -A -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${USER}@${NODE}" bash -s <<'PROBE_EOF'
echo "hostname: $(hostname)"
echo ""

echo "--- GPU Status ---"
rocm-smi --showuse 2>/dev/null | head -20 || echo "rocm-smi: unavailable"
echo ""

echo "--- GPU Memory ---"
rocm-smi --showmeminfo vram 2>/dev/null | head -30 || echo "GPU mem info: unavailable"
echo ""

echo "--- GPU Processes ---"
rocm-smi --showpids 2>/dev/null | head -15 || echo "No active GPU processes"
echo ""

echo "--- Disk Space ---"
df -h /tmp /data /home 2>/dev/null || df -h / 2>/dev/null
echo ""

echo "--- Python ---"
python3 --version 2>/dev/null || echo "python3: not found"
echo ""

echo "--- Cached Models ---"
for dir in /data/cache/models /tmp/cache/models; do
  if [ -d "$dir" ]; then
    echo "  $dir:"
    ls -1 "$dir" 2>/dev/null | sed 's/^/    /'
  fi
done
# Also check HuggingFace cache
HF_DIR="${HF_HOME:-$HOME/.cache/huggingface}/hub"
if [ -d "$HF_DIR" ]; then
  echo "  HuggingFace cache ($HF_DIR):"
  ls -1 "$HF_DIR" 2>/dev/null | grep "^models--" | sed 's/^models--//; s/--/\//g; s/^/    /' | head -10
fi
# Check overnight-tests for model artifacts
if [ -d "/tmp/overnight-tests" ]; then
  echo "  Overnight workdir repos:"
  ls -1 /tmp/overnight-tests/ 2>/dev/null | grep -v "^logs$" | sed 's/^/    /'
fi
echo ""

echo "--- Cached Datasets ---"
for dir in /data/cache/datasets /tmp/cache/datasets; do
  if [ -d "$dir" ]; then
    echo "  $dir:"
    ls -1 "$dir" 2>/dev/null | sed 's/^/    /'
  fi
done
echo ""

echo "--- Data Volume Check ---"
if mountpoint -q /data 2>/dev/null; then
  echo "  /data: MOUNTED"
  df -h /data
else
  echo "  /data: NOT MOUNTED (using /tmp as fallback)"
fi
echo ""

echo "--- Docker Disk Usage ---"
docker system df 2>/dev/null || echo "  Docker: not available or no permission"
STOPPED=$(docker ps -a --filter "status=exited" -q 2>/dev/null | wc -l)
echo "  Stopped containers: $STOPPED"
if [ "$STOPPED" -gt 5 ]; then
  echo "  WARNING: $STOPPED stopped containers — consider 'docker system prune -f'"
fi
echo ""

echo "=== Probe Complete ==="
PROBE_EOF

PROBE_EXIT=$?
if [ $PROBE_EXIT -ne 0 ]; then
  echo "ERROR: Node $NODE unreachable or probe failed (exit $PROBE_EXIT)"
fi
