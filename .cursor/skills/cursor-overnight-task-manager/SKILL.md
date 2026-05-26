---
name: cursor-overnight-task-manager
version: 1.0.0
author: ZJLi2013
description: >-
  批量夜间自动测试开源 GitHub 仓库的工作流。读取 input-list.txt 中的 repo 地址，
  SSH 到远端 AMD GPU 节点，自动完成 clone、依赖安装、数据集/checkpoint 下载、
  headless 运行、结果收集与分析。Use when user mentions overnight testing,
  batch repo testing, AMD GPU testing, input-list, or headless run. This skill
  owns the concrete batch execution workflow; use long-running-agent-harness
  for multi-session planning, progress tracking, and handoff.
allowed-tools: [Shell]
---

# Cursor Overnight Task Manager

批量挂任务过夜：读取 repo 列表 → SSH 到远端 AMD GPU → clone → setup → run → 收集结果 → 生成报告。

## 与 long-running-agent-harness 的边界

- `cursor-overnight-task-manager` 负责实际批量执行：读取 `input-list.txt`、选节点、远端 setup、headless run、收集结果。
- `long-running-agent-harness` 负责长期任务总控：任务拆解、runbook、进度日志、验证门槛和交接。
- 如果 overnight run 是一个更大任务的一部分，先用 harness 建立 `.cursor/harness/`，再按本 skill 执行批量测试。

## 先决条件

- 本机可 SSH 到远端（推荐 SSH Agent Forwarding，参考 `remote-ssh-github-auto` skill）
- 远端已安装 ROCm 运行时（`rocminfo` 可用）
- 远端有 Python 3.8+、pip、git
- 远端有足够磁盘空间（模型 checkpoint + 数据集）

## 输入文件

### input-list.txt（必需）

每行一个 GitHub repo 地址，支持注释和可选参数：

```
# 格式: <github_url> [branch] [run_command]
# 空行和 # 开头的行会被跳过

https://github.com/huggingface/transformers  main  "python examples/pytorch/text-classification/run_glue.py --model_name_or_path bert-base-uncased --task_name mrpc --do_eval --max_seq_length 128 --output_dir /tmp/mrpc"
https://github.com/facebookresearch/detectron2  main
https://github.com/openai/whisper
```

- 只写 URL → 自动检测 `README.md` / `setup.py` / `Makefile` 中的测试命令
- 指定 branch → 切到该分支
- 指定 run_command → 覆盖自动检测，直接执行该命令

### 节点配置

远端节点配置有两种格式（与其他 skill 共享）：

- **推荐**：`.cursor/configs/node_inventory.yaml` — 含 GPU 类型、磁盘、数据/模型标签（`gpu-cluster-resource-manager` skill 管理）
- **回退**：`.cursor/configs/gpu_nodes.list` — 仅主机名列表，每行一个

---

## 工作流（逐步执行）

### Phase 0: 节点探测与亲和性调度

> **委托 `gpu-cluster-resource-manager` skill 执行。** 详细流程见该 skill。

核心步骤：
1. 读取 `node_inventory.yaml` → 候选节点 + 静态标签（已缓存的 models/datasets）
2. 并行 SSH 探测：GPU 空闲度、磁盘剩余、缓存状态
3. 解析本批 repo 的依赖需求（需要哪些 models/datasets）
4. 亲和性打分：数据命中(+10) + GPU 空闲(+5) + 磁盘充足(+5) − 负载惩罚(−2)
5. 输出节点分配方案（score 最高 → 优先分配）

磁盘硬约束：< 20G 直接排除，< 50G 仅分配轻量任务。

预检失败则停止并报告，不浪费时间。

### Phase 1: 解析 input-list.txt

```bash
# 跳过注释和空行，解析每行
grep -v '^\s*#' input-list.txt | grep -v '^\s*$' | while IFS= read -r line; do
  repo_url=$(echo "$line" | awk '{print $1}')
  branch=$(echo "$line" | awk '{print $2}')
  run_cmd=$(echo "$line" | sed 's/^[^ ]* *[^ ]* *//' | sed 's/^"//;s/"$//')
  repo_name=$(basename "$repo_url" .git)
  echo "REPO: $repo_name | BRANCH: ${branch:-HEAD} | CMD: ${run_cmd:-auto-detect}"
done
```

### Phase 2: 远端 Clone / Update

对每个 repo，在远端执行：

```bash
WORKDIR="/tmp/overnight-tests"
ssh -A $node bash -s <<'REMOTE_SCRIPT'
  set -euo pipefail
  mkdir -p $WORKDIR && cd $WORKDIR

  if [ -d "$REPO_NAME" ]; then
    cd "$REPO_NAME"
    git fetch origin
    git checkout ${BRANCH:-HEAD}
    git pull --ff-only
  else
    git clone "$REPO_URL" "$REPO_NAME"
    cd "$REPO_NAME"
    [ -n "${BRANCH:-}" ] && git checkout "$BRANCH"
  fi
REMOTE_SCRIPT
```

### Phase 3: 依赖安装与环境准备

远端自动检测并安装依赖：

```bash
ssh -A $node bash -s <<'REMOTE_SCRIPT'
  cd $WORKDIR/$REPO_NAME
  
  # 创建 venv 隔离环境
  python3 -m venv .venv --system-site-packages
  source .venv/bin/activate

  # 按优先级检测依赖文件
  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
  elif [ -f "setup.py" ] || [ -f "pyproject.toml" ]; then
    pip install -e ".[dev,test]" 2>/dev/null || pip install -e .
  elif [ -f "environment.yml" ]; then
    conda env update -f environment.yml
  fi

  # AMD GPU: 确保 PyTorch ROCm 版本
  python3 -c "import torch; print(f'PyTorch {torch.__version__}, ROCm: {torch.version.hip}')" 2>/dev/null || \
    echo "WARN: PyTorch ROCm not detected"
REMOTE_SCRIPT
```

### Phase 4: 数据集 / Checkpoint 下载

自动检测并下载常见资源：

```bash
ssh -A $node bash -s <<'REMOTE_SCRIPT'
  cd $WORKDIR/$REPO_NAME
  source .venv/bin/activate

  # 扫描 README/config 中的常见下载模式
  # huggingface model
  grep -r "from_pretrained\|AutoModel\|AutoTokenizer" --include="*.py" -l | head -5 && \
    echo "INFO: HuggingFace models will auto-download on first run"

  # 显式下载脚本
  if [ -f "scripts/download_data.sh" ]; then
    bash scripts/download_data.sh
  elif [ -f "download.py" ]; then
    python3 download.py
  elif [ -f "data/download.sh" ]; then
    bash data/download.sh
  fi

  # gdown / wget 链接（从 README 提取）
  grep -oP 'https://drive\.google\.com/[^\s)"]+' README.md 2>/dev/null | head -3 && \
    echo "WARN: Google Drive links found — may need manual download"
REMOTE_SCRIPT
```

### Phase 5: Headless 运行

```bash
LOGDIR="/tmp/overnight-tests/logs/$REPO_NAME"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

ssh -A $node bash -s <<REMOTE_SCRIPT
  set -euo pipefail
  cd $WORKDIR/$REPO_NAME
  source .venv/bin/activate
  mkdir -p "$LOGDIR"

  export HIP_VISIBLE_DEVICES=0
  export HSA_OVERRIDE_GFX_VERSION=11.0.0  # 按实际 GPU 调整
  export PYTORCH_HIP_ALLOC_CONF=expandable_segments:True

  # 如果用户指定了命令，直接用；否则自动检测
  if [ -n "${RUN_CMD:-}" ]; then
    FINAL_CMD="$RUN_CMD"
  elif [ -f "Makefile" ] && grep -q "^test:" Makefile; then
    FINAL_CMD="make test"
  elif [ -f "pytest.ini" ] || [ -f "setup.cfg" ] || [ -d "tests" ]; then
    FINAL_CMD="python3 -m pytest tests/ -x -v --timeout=600"
  elif ls examples/*.py 1>/dev/null 2>&1; then
    FINAL_CMD="python3 \$(ls examples/*.py | head -1) --help"
  else
    FINAL_CMD="echo 'NO_AUTO_DETECT: specify run_command in input-list.txt'"
  fi

  echo "=== RUN: \$FINAL_CMD ===" | tee "$LOGDIR/run_${TIMESTAMP}.log"
  echo "=== START: \$(date) ===" | tee -a "$LOGDIR/run_${TIMESTAMP}.log"

  timeout 7200 bash -c "\$FINAL_CMD" \
    >> "$LOGDIR/run_${TIMESTAMP}.log" 2>&1
  EXIT_CODE=\$?

  echo "=== END: \$(date) | EXIT_CODE: \$EXIT_CODE ===" | tee -a "$LOGDIR/run_${TIMESTAMP}.log"

  # 收集 GPU 使用信息
  rocm-smi >> "$LOGDIR/gpu_${TIMESTAMP}.log" 2>/dev/null
REMOTE_SCRIPT
```

### Phase 6: 结果回传与分析

```bash
# 从远端拉取日志到本地
LOCAL_RESULTS="./overnight-results/$(date +%Y%m%d)"
mkdir -p "$LOCAL_RESULTS"

for node in $nodes; do
  scp -r "$node:/tmp/overnight-tests/logs/*" "$LOCAL_RESULTS/$node/" 2>/dev/null
done

# 执行分析（见 scripts/analyze-results.py）
python3 scripts/analyze-results.py "$LOCAL_RESULTS" --output "$LOCAL_RESULTS/report.md"
```

### Phase 7: 自动 Fork & PR（可选）

当测试中发现需要给上游提交修复（如 ROCm 兼容性），自动 fork 并创建 PR branch：

```bash
# ---- 配置 ----
UPSTREAM_URL="$REPO_URL"                          # e.g. https://github.com/H-EmbodVis/HyDRA.git
UPSTREAM_OWNER=$(echo "$UPSTREAM_URL" | sed -n 's|.*github\.com/\([^/]*\)/.*|\1|p')
UPSTREAM_REPO=$(basename "$UPSTREAM_URL" .git)
GH_USER="ZJLi2013"                                # 你的 GitHub 用户名
GH_TOKEN="${GITHUB_TOKEN}"                         # PAT (需要 repo scope)
LOCAL_FORK_DIR="${LOCAL_FORK_ROOT:-$HOME/github/3D_World}/$UPSTREAM_REPO"
PR_BRANCH="feat/rocm-compat"                       # PR 分支名，按实际改

# ---- Step 1: GitHub API 创建 Fork ----
echo ">>> Forking $UPSTREAM_OWNER/$UPSTREAM_REPO → $GH_USER/$UPSTREAM_REPO"
curl -sf -X POST \
  -H "Authorization: token $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$UPSTREAM_OWNER/$UPSTREAM_REPO/forks" \
  -d "{\"default_branch_only\": true}" \
  -o /dev/null && echo "Fork created (or already exists)" || echo "Fork API call failed"

# GitHub fork 是异步的，等待最多 30 秒
for i in $(seq 1 6); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "https://api.github.com/repos/$GH_USER/$UPSTREAM_REPO")
  [ "$HTTP_CODE" = "200" ] && break
  echo "  waiting for fork to be ready... ($i/6)"
  sleep 5
done

# ---- Step 2: 本地 Clone（如果不存在）并添加 remote ----
if [ ! -d "$LOCAL_FORK_DIR/.git" ]; then
  echo ">>> Cloning upstream to $LOCAL_FORK_DIR"
  git clone "$UPSTREAM_URL" "$LOCAL_FORK_DIR"
fi
cd "$LOCAL_FORK_DIR"

# 确保 upstream 和 myfork 两个 remote 都存在
git remote get-url upstream 2>/dev/null || git remote add upstream "$UPSTREAM_URL"
git remote get-url myfork   2>/dev/null || git remote add myfork "https://github.com/$GH_USER/$UPSTREAM_REPO.git"

git fetch upstream
git fetch myfork 2>/dev/null || true

# ---- Step 3: 创建 PR branch（基于 upstream/main）----
git checkout -B "$PR_BRANCH" upstream/main

# >>> 在这里做代码改动（通常由 agent 完成）<<<

# ---- Step 4: Push PR branch 到 fork ----
git push -u myfork "$PR_BRANCH"

# ---- Step 5: GitHub API 创建 Pull Request ----
PR_TITLE="Add AMD ROCm support"
PR_BODY="## Summary\n- Improve attention backend robustness\n- Add ROCm installation docs\n\nTested on AMD MI300X + ROCm 6.4."

PR_RESPONSE=$(curl -sf -X POST \
  -H "Authorization: token $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$UPSTREAM_OWNER/$UPSTREAM_REPO/pulls" \
  -d "{
    \"title\": \"$PR_TITLE\",
    \"body\": \"$PR_BODY\",
    \"head\": \"$GH_USER:$PR_BRANCH\",
    \"base\": \"main\"
  }")

PR_URL=$(echo "$PR_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('html_url','PR creation failed'))" 2>/dev/null)
echo ">>> PR created: $PR_URL"
```

**前提条件**：
- 环境变量 `GITHUB_TOKEN` 需要设置（Personal Access Token，需 `repo` scope）
- 如果在 Windows PowerShell 中执行，建议写成 `.sh` 脚本 SCP 到远端或用 WSL 执行
- Fork 仅包含代码/文档改动，实验记录（`experiments.md`、`overnight-results/`）不进入 PR branch

---

## AMD GPU 常见问题速查

| 问题 | 解法 |
|------|------|
| `hipErrorNoBinaryForGpu` | 设置 `HSA_OVERRIDE_GFX_VERSION` 匹配 GPU 架构 |
| OOM `HIP out of memory` | 减小 batch_size，或设 `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True` |
| NCCL 多卡挂死 | `export NCCL_P2P_DISABLE=1`，或升级 ROCm RCCL |
| `torch.cuda.is_available()` 返回 False | 确认 `rocminfo` 有输出且 PyTorch 为 ROCm 版 |
| 算子不支持 | 回退到 CPU: `CUDA_VISIBLE_DEVICES=""` 跑基线对比 |

## 报告模板

每次 overnight run 生成 `report.md`：

```markdown
# Overnight Test Report — YYYY-MM-DD

## Summary
| Repo | Node | Status | Duration | Key Metric |
|------|------|--------|----------|------------|
| transformers | gpu01 | PASS | 45m | MRPC acc=86.2% |
| detectron2 | gpu01 | FAIL | 12m | OOM at batch=8 |

## Per-Repo Details

### <repo_name>
- **Branch**: main
- **Command**: `...`
- **Exit Code**: 0
- **Duration**: 45m
- **Log Tail** (last 30 lines): ...
- **GPU Memory Peak**: 14.2 GiB
- **Errors/Warnings**: none

## AMD GPU Compatibility Notes
- <issues encountered and workarounds applied>

## Next Steps
- [ ] Fix OOM for detectron2 — try batch_size=4
- [ ] Re-run whisper with larger dataset
```

## 辅助脚本

- `scripts/overnight-runner.sh` — 主批量执行脚本（一键启动）
- `scripts/analyze-results.py` — 日志解析与报告生成

### Phase 完成后: 更新节点标签

每次 overnight batch 完成后，调用 `gpu-cluster-resource-manager` 的探测脚本更新 `node_inventory.yaml` 中的 labels（新下载的 models/datasets）。

---

## 与其他 Skill 的协作

- **gpu-cluster-resource-manager**：Phase 0 委托执行节点探测 + 亲和性调度 + 存储治理；Phase 完成后更新标签
- **remote-ssh-github-auto**：SSH 连接与 GitHub 认证（Phase 0 依赖）
- **rocm-lib-compat**：ROCm 库替换表，flash-attn / triton / aiter 等安装方式（Phase 3 依赖）
- **local-push-remote-pull-test**：如果需要测试自己的 fork，先 push 再 pull
- **experiment-driven-doc**：对复杂实验结果做假设-验证追踪（Phase 6 → Phase 7 衔接）
- **long-running-agent-harness**：负责 overnight 工作外层的任务拆解、runbook、进度日志和 handoff
- **agent-heartbeat**：长任务执行时的心跳提示
