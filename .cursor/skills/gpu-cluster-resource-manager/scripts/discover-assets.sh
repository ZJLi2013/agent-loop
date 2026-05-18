#!/usr/bin/env bash
# discover-assets.sh — Scan a remote GPU node for scattered model/dataset files
# Usage: bash discover-assets.sh <hostname> [user] [--link]
#   --link: auto-create symlinks to unified cache (default: report only)

set -o pipefail

NODE="${1:?Usage: discover-assets.sh <hostname> [user] [--link]}"
USER="${2:-zhengjli}"
DO_LINK="${3:-}"

echo "=== Asset Discovery: $NODE ==="
[ "$DO_LINK" = "--link" ] && echo "Mode: DISCOVER + LINK" || echo "Mode: DISCOVER ONLY (use --link to create symlinks)"

ssh -A -o ConnectTimeout=10 "${USER}@${NODE}" bash -s -- "$DO_LINK" <<'DISCOVER_EOF'
DO_LINK="$1"
CACHE_ROOT="/data/cache"
[ ! -d "$CACHE_ROOT" ] && CACHE_ROOT="/tmp/cache"
mkdir -p "${CACHE_ROOT}/models" "${CACHE_ROOT}/datasets" 2>/dev/null

echo ""
echo "Unified cache root: $CACHE_ROOT"
echo ""

# -------------------------------------------------------------------
# 1. Large model files (safetensors, bin, pt, ckpt) > 500MB
# -------------------------------------------------------------------
echo "--- Large model files (>500MB) ---"
find /home /tmp /data /opt -type f \
  \( -name "*.safetensors" -o -name "*.bin" -o -name "*.pt" -o -name "*.pth" \
     -o -name "*.ckpt" -o -name "*.onnx" -o -name "*.msgpack" \) \
  -size +500M 2>/dev/null | while read f; do
  SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
  echo "  $SIZE  $f"
done | sort -rh | head -30
echo ""

# -------------------------------------------------------------------
# 2. HuggingFace cache directories (all users)
# -------------------------------------------------------------------
echo "--- HuggingFace caches found ---"
HF_DIRS=$(find /home /tmp /root -maxdepth 5 -type d -name "hub" -path "*/huggingface/*" 2>/dev/null)
for hf_hub in $HF_DIRS; do
  hf_dir=$(dirname "$hf_hub")
  SIZE=$(du -sh "$hf_dir" 2>/dev/null | cut -f1)
  OWNER=$(stat -c '%U' "$hf_dir" 2>/dev/null || echo "unknown")
  echo "  $SIZE  $hf_dir  (owner: $OWNER)"
  ls -1 "$hf_hub" 2>/dev/null | grep "^models--" | sed 's/^models--//; s/--/\//g; s/^/         /' | head -10
done
echo ""

# -------------------------------------------------------------------
# 3. Known foundation models — keyword scan
# -------------------------------------------------------------------
echo "--- Known foundation models ---"
KNOWN="sam2\|segment.anything\|dinov2\|dino-v2\|siglip\|sig-lip\|clip-vit\|wan2\|depth.anything\|stable.diffusion\|llava\|whisper\|paligemma\|openvla"

find /home /tmp /data -maxdepth 6 -type d 2>/dev/null | grep -i "$KNOWN" | while read d; do
  if [ -r "$d" ]; then
    SIZE=$(du -sh "$d" 2>/dev/null | cut -f1)
    OWNER=$(stat -c '%U' "$d" 2>/dev/null || echo "unknown")
    BASENAME=$(basename "$d")
    echo "  $SIZE  $d  (owner: $OWNER)"

    # Auto-link if --link mode and not already in cache
    if [ "$DO_LINK" = "--link" ]; then
      LINK_NAME=$(echo "$BASENAME" | tr '[:upper:]' '[:lower:]' | sed 's/models--//; s/--/-/g')
      LINK_TARGET="${CACHE_ROOT}/models/${LINK_NAME}"
      if [ ! -e "$LINK_TARGET" ] && [ -r "$d" ]; then
        ln -s "$d" "$LINK_TARGET" 2>/dev/null && echo "    → LINKED to $LINK_TARGET"
      elif [ -L "$LINK_TARGET" ]; then
        echo "    → already linked: $LINK_TARGET → $(readlink "$LINK_TARGET")"
      fi
    fi
  fi
done | sort -rh
echo ""

# -------------------------------------------------------------------
# 4. Large dataset directories (common patterns)
# -------------------------------------------------------------------
echo "--- Potential dataset directories ---"
DATASET_PATTERNS="imagenet\|coco\|scannet\|oxe\|lerobot\|openx\|bridge\|kitti\|nuscenes\|waymo\|shapenet"
find /home /tmp /data -maxdepth 4 -type d 2>/dev/null | grep -i "$DATASET_PATTERNS" | while read d; do
  if [ -r "$d" ]; then
    SIZE=$(du -sh "$d" 2>/dev/null | cut -f1)
    OWNER=$(stat -c '%U' "$d" 2>/dev/null || echo "unknown")
    echo "  $SIZE  $d  (owner: $OWNER)"

    if [ "$DO_LINK" = "--link" ]; then
      LINK_NAME=$(basename "$d" | tr '[:upper:]' '[:lower:]')
      LINK_TARGET="${CACHE_ROOT}/datasets/${LINK_NAME}"
      if [ ! -e "$LINK_TARGET" ] && [ -r "$d" ]; then
        ln -s "$d" "$LINK_TARGET" 2>/dev/null && echo "    → LINKED to $LINK_TARGET"
      fi
    fi
  fi
done | sort -rh
echo ""

# -------------------------------------------------------------------
# 5. Summary: what's already in unified cache
# -------------------------------------------------------------------
echo "--- Unified cache contents ---"
echo "  Models:"
ls -la "${CACHE_ROOT}/models/" 2>/dev/null | tail -n +2 | sed 's/^/    /'
echo "  Datasets:"
ls -la "${CACHE_ROOT}/datasets/" 2>/dev/null | tail -n +2 | sed 's/^/    /'
echo ""

echo "=== Discovery Complete ==="
DISCOVER_EOF

DISCOVER_EXIT=$?
if [ $DISCOVER_EXIT -ne 0 ]; then
  echo "ERROR: Node $NODE unreachable or discovery failed (exit $DISCOVER_EXIT)"
fi
