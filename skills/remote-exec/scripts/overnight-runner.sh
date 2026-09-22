#!/usr/bin/env bash
set -euo pipefail

#
# overnight-runner.sh — batch clone/setup/run for repos listed in input-list.txt
#
# Usage:
#   bash scripts/overnight-runner.sh [input-list.txt] [gpu_nodes.list]
#
# Defaults:
#   input-list.txt         = ./input-list.txt
#   gpu_nodes.list         = .cursor/configs/gpu_nodes.list
#

INPUT_FILE="${1:-./input-list.txt}"
NODES_FILE="${2:-.cursor/configs/gpu_nodes.list}"
REMOTE_WORKDIR="/tmp/overnight-tests"
LOCAL_RESULTS="./overnight-results/$(date +%Y%m%d)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TIMEOUT_SEC=7200  # 2 hours per repo

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*"; }

# --- Validate inputs ---
if [ ! -f "$INPUT_FILE" ]; then
  err "Input file not found: $INPUT_FILE"
  echo "Create it from the example: cp input-list.txt.example input-list.txt"
  exit 1
fi

if [ ! -f "$NODES_FILE" ]; then
  err "Node list not found: $NODES_FILE"
  echo "Create it: cp .cursor/configs/gpu_nodes.list.example .cursor/configs/gpu_nodes.list"
  exit 1
fi

# --- Read nodes ---
mapfile -t NODES < <(grep -v '^\s*#' "$NODES_FILE" | grep -v '^\s*$')
if [ ${#NODES[@]} -eq 0 ]; then
  err "No nodes found in $NODES_FILE"
  exit 1
fi
log "Nodes: ${NODES[*]}"

# --- Pre-flight check ---
log "=== Phase 0: Pre-flight check ==="
for node in "${NODES[@]}"; do
  log "Checking $node ..."
  ssh -A -o ConnectTimeout=10 "$node" bash -s <<'EOF' || { err "Pre-flight FAILED on $node"; exit 1; }
    echo "--- ROCm ---"
    rocminfo 2>/dev/null | grep -E "Name:|Marketing" | head -4 || echo "rocminfo not found"
    echo "--- Python ---"
    python3 --version 2>/dev/null || echo "python3 not found"
    echo "--- Disk ---"
    df -h /tmp | tail -1
EOF
done
log "Pre-flight passed on all nodes."

# --- Parse repos ---
log "=== Phase 1: Parsing $INPUT_FILE ==="
mapfile -t REPO_LINES < <(grep -v '^\s*#' "$INPUT_FILE" | grep -v '^\s*$')
log "Found ${#REPO_LINES[@]} repo(s)"

mkdir -p "$LOCAL_RESULTS"
SUMMARY_FILE="$LOCAL_RESULTS/summary.csv"
echo "repo,node,branch,exit_code,duration_sec,log_file" > "$SUMMARY_FILE"

# --- Main loop: round-robin repos across nodes ---
node_idx=0
for line in "${REPO_LINES[@]}"; do
  repo_url=$(echo "$line" | awk '{print $1}')
  branch=$(echo "$line" | awk '{print $2}')
  run_cmd=$(echo "$line" | sed 's/^[^ ]* *//' | sed 's/^[^ ]* *//' | sed 's/^"//;s/"$//')

  repo_name=$(basename "$repo_url" .git)
  node="${NODES[$node_idx]}"
  node_idx=$(( (node_idx + 1) % ${#NODES[@]} ))

  log "=== Processing: $repo_name on $node (branch: ${branch:-HEAD}) ==="

  LOGFILE="$LOCAL_RESULTS/${repo_name}_${node##*@}.log"
  START_TIME=$(date +%s)

  # Phase 2-5: remote execution
  ssh -A -o ConnectTimeout=30 "$node" bash -s -- \
    "$repo_url" "$repo_name" "${branch:-}" "${run_cmd:-}" "$REMOTE_WORKDIR" "$TIMEOUT_SEC" \
    > "$LOGFILE" 2>&1 <<'REMOTE' || true
    set -uo pipefail
    REPO_URL="$1"; REPO_NAME="$2"; BRANCH="$3"; RUN_CMD="$4"
    WORKDIR="$5"; TIMEOUT="$6"

    echo "=== REMOTE START: $(date) ==="
    echo "=== REPO: $REPO_URL | BRANCH: ${BRANCH:-HEAD} ==="

    # Phase 2: Clone / Update
    mkdir -p "$WORKDIR" && cd "$WORKDIR"
    if [ -d "$REPO_NAME" ]; then
      echo "[clone] Updating existing repo..."
      cd "$REPO_NAME"
      git fetch origin
      [ -n "$BRANCH" ] && git checkout "$BRANCH"
      git pull --ff-only || git reset --hard "origin/${BRANCH:-HEAD}"
    else
      echo "[clone] Cloning fresh..."
      git clone "$REPO_URL" "$REPO_NAME"
      cd "$REPO_NAME"
      [ -n "$BRANCH" ] && git checkout "$BRANCH"
    fi
    echo "[clone] OK — $(git log --oneline -1)"

    # Phase 3: Dependencies
    echo "[setup] Installing dependencies..."
    python3 -m venv .venv --system-site-packages 2>/dev/null || true
    if [ -f ".venv/bin/activate" ]; then
      source .venv/bin/activate
    fi

    if [ -f "requirements.txt" ]; then
      pip install -q -r requirements.txt 2>&1 | tail -5
    elif [ -f "pyproject.toml" ]; then
      pip install -q -e ".[dev,test]" 2>&1 | tail -5 || pip install -q -e . 2>&1 | tail -5
    elif [ -f "setup.py" ]; then
      pip install -q -e ".[dev,test]" 2>&1 | tail -5 || pip install -q -e . 2>&1 | tail -5
    elif [ -f "environment.yml" ]; then
      echo "[setup] Conda environment.yml detected — skipping (manual setup needed)"
    else
      echo "[setup] No dependency file found"
    fi

    python3 -c "import torch; print(f'PyTorch {torch.__version__}, HIP: {torch.version.hip}')" 2>/dev/null || \
      echo "[setup] WARN: PyTorch ROCm not available"

    # Phase 4: Data / Checkpoint detection
    echo "[data] Scanning for download scripts..."
    for f in scripts/download_data.sh scripts/download.sh data/download.sh download.py; do
      if [ -f "$f" ]; then
        echo "[data] Running $f ..."
        timeout 1800 bash -c "[ '${f##*.}' = 'py' ] && python3 '$f' || bash '$f'" 2>&1 | tail -10
        break
      fi
    done

    # Phase 5: Headless run
    export HIP_VISIBLE_DEVICES=0
    export PYTORCH_HIP_ALLOC_CONF=expandable_segments:True

    if [ -n "$RUN_CMD" ]; then
      FINAL_CMD="$RUN_CMD"
    elif [ -f "Makefile" ] && grep -q "^test:" Makefile; then
      FINAL_CMD="make test"
    elif [ -f "pytest.ini" ] || [ -f "setup.cfg" ] || [ -d "tests" ]; then
      FINAL_CMD="python3 -m pytest tests/ -x -v --timeout=600 2>&1"
    elif ls examples/*.py 1>/dev/null 2>&1; then
      FINAL_CMD="python3 $(ls examples/*.py | head -1) --help"
    else
      FINAL_CMD="echo 'NO_AUTO_DETECT: specify run_command in input-list.txt'"
    fi

    echo "=== RUN: $FINAL_CMD ==="
    echo "=== RUN_START: $(date) ==="
    timeout "$TIMEOUT" bash -c "$FINAL_CMD" 2>&1
    EXIT_CODE=$?
    echo "=== RUN_END: $(date) | EXIT_CODE: $EXIT_CODE ==="

    # GPU snapshot
    rocm-smi 2>/dev/null || true

    exit $EXIT_CODE
REMOTE

  EXIT_CODE=$?
  END_TIME=$(date +%s)
  DURATION=$(( END_TIME - START_TIME ))

  if [ $EXIT_CODE -eq 0 ]; then
    log "$repo_name — ${GREEN}PASS${NC} (${DURATION}s)"
  else
    warn "$repo_name — ${RED}FAIL (exit=$EXIT_CODE)${NC} (${DURATION}s)"
  fi

  echo "$repo_name,$node,${branch:-HEAD},$EXIT_CODE,$DURATION,$LOGFILE" >> "$SUMMARY_FILE"
done

log "=== All repos processed. Results in $LOCAL_RESULTS ==="
log "Summary: $SUMMARY_FILE"

# Phase 6: Generate report
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/analyze-results.py" ]; then
  log "Generating report..."
  python3 "$SCRIPT_DIR/analyze-results.py" "$LOCAL_RESULTS" --output "$LOCAL_RESULTS/report.md"
  log "Report: $LOCAL_RESULTS/report.md"
fi
