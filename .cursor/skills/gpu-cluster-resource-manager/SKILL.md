---
name: gpu-cluster-resource-manager
version: 1.0.0
author: ZJLi2013
description: >-
  轻量级多节点 GPU 集群资源管理：实时资源探测、数据/模型亲和性调度、存储治理。
  在分配 repo 测试任务到远端 GPU 节点前，自动选择最优节点。
  Use when probing GPU nodes, selecting nodes for tasks, checking disk space,
  managing cached datasets/models, or cleaning up storage on remote nodes.
allowed-tools: [Shell]
---

# GPU Cluster Resource Manager

轻量级多节点资源调度：探测 → 打分 → 选节点 → 管存储。

**三层架构**：
1. **资源可见性** — 实时探测 GPU / 磁盘 / 缓存状态
2. **亲和性调度** — 按数据命中 + 资源空闲度打分选节点
3. **存储治理** — 数据分级 + 清理策略

---

## 配置文件



### gpu_nodes.list（节点清单 — 已有）

路径：`.cursor/configs/gpu_nodes.list`（已 gitignore）

```
# 格式：每行一个 SSH 主机名，# 开头为注释
# Hot nodes（优先使用，维护 top 5）标注 [hot]

<node-1>.example.dcgpu    # [hot] MI308X, 3.0T disk
<node-2>.example.dcgpu    # [hot] MI300X, 686G
<node-3>.example.dcgpu    # [hot] MI300X
<node-4>.example.dcgpu    # [hot] MI300X
<node-5>.example.dcgpu    # [hot] MI350X
# --- cold pool (按需启用) ---
<node-6>.example.dcgpu
<node-7>.example.dcgpu
...
```

### node_inventory.yaml（带标签的丰富配置 — 可选）

路径：`.cursor/configs/node_inventory.yaml`（已 gitignore）

```yaml
defaults:
  user: <your_username>
  cache_root: /data/cache
  cache_fallback: /tmp/cache
  workdir: /tmp/overnight-tests
  hot_models:          # 永不清理的基础模型
    - sam2
    - dinov2
    - siglip
    - wan2.1
    - da3-depth

# Hot Nodes: top 5 常用节点，大部分 overnight 任务在这 5 台上执行
#
# storage_type:
#   A — 独立 /data RAID 挂载 (md127 等)，大容量持久存储
#   B — 仅大 root 分区，无独立 /data，回退到 /tmp
#
# data_dir: 自动检测结果（A 型 → /data, B 型 → /tmp）

hot_nodes:
  <node-1>:
    gpu_type: MI308X
    gpu_count: 8
    arch: gfx942
    storage_type: B             # 无独立 /data，root 3.5T
    disk_total: "3.5T"
    data_dir: /tmp
    labels:
      models: [wan2.1, dinov2]
      datasets: []
    notes: "大 root 分区，首选节点"

  <node-2>:
    gpu_type: MI300X
    gpu_count: 8
    arch: gfx942
    storage_type: A             # /dev/md127 → /data (11T)
    disk_total: "11T /data + 3.5T /"
    data_dir: /data
    labels:
      models: [siglip, llava-video-7b]
      datasets: []
    notes: "Python 3.13 默认 — 需 3.11 venv; root 分区紧张 (98%)"

  <node-3>:
    gpu_type: MI300X
    gpu_count: 8
    arch: gfx942
    storage_type: A             # /dev/md127 → /data (3.5T)
    disk_total: "3.5T /data + 879G /"
    data_dir: /data
    labels:
      models: []
      datasets: []
    notes: "root 分区满 (100%, 4.6G free) — 仅可用 /data"

  <node-4>:
    gpu_type: MI300X
    gpu_count: 8
    arch: gfx942
    storage_type: B             # 无独立 /data，root 1.8T
    disk_total: "1.8T"
    data_dir: /tmp
    labels:
      models: []
      datasets: []

  <node-5>:
    gpu_type: MI350
    gpu_count: 8
    arch: gfx950
    storage_type: unknown       # 待首次探测
    disk_total: "1T"
    data_dir: auto
    labels:
      models: []
      datasets: []

# Cold pool: 大量备用节点，仅在 hot nodes 不可用时启用
# cold_nodes 直接从 gpu_nodes.list 读取（不需要标签）
```

### Hot Nodes 策略

**核心思想**：30+ 节点的资源池中，只维护 **top 5 hot nodes** 用于日常 overnight 测试。

| 分类 | 数量 | 用途 | 管理粒度 |
|------|------|------|---------|
| **Hot** | 5 台 | 日常 overnight 任务 | 精细标签 + 缓存管理 + 定期清理 |
| **Cold** | 25+ 台 | 仅在 hot 全忙/不可达时回退 | 仅探测可达性 + 磁盘 |


**回退策略**：如果 hot nodes 全部不可用（磁盘满/GPU 被占/SSH 不通），才从 cold pool 中探测选择。

---

## Layer 1: 资源可见性

### 1.1 标准化探测脚本

对每个节点 SSH 探测，输出结构化 JSON：

```bash
USER="${GPU_USER:-zhengjli}"   # 从环境变量或默认值
NODE="$1"

ssh -A -o ConnectTimeout=10 ${USER}@${NODE} bash -s <<'PROBE_SCRIPT'
set -o pipefail
echo "{"

# hostname
echo "  \"node\": \"$(hostname)\","

# GPU: free memory (MiB) and utilization (%)
GPU_MEM=$(rocm-smi --showmeminfo vram --json 2>/dev/null)
GPU_UTIL=$(rocm-smi --showuse --json 2>/dev/null)
if [ -n "$GPU_MEM" ]; then
  echo "  \"gpu_info\": $GPU_MEM,"
  echo "  \"gpu_util\": $GPU_UTIL,"
else
  echo "  \"gpu_info\": null,"
  echo "  \"gpu_util\": null,"
fi

# Disk: free space on key mounts + /data existence check
echo "  \"has_data_mount\": $(mountpoint -q /data 2>/dev/null && echo 'true' || echo 'false'),"
echo "  \"has_data_dir\": $([ -d /data ] && echo 'true' || echo 'false'),"
echo "  \"disk\": {"
for mnt in /tmp /data /home /; do
  [ -d "$mnt" ] && df -BG --output=target,avail "$mnt" 2>/dev/null | tail -n +2 | while read mount avail; do
    echo "    \"$mount\": \"$avail\","
  done
done | sort -u
echo "  },"

# Cached models (scan known cache dirs)
echo "  \"cached_models\": ["
for dir in /data/cache/models /tmp/cache/models /tmp/overnight-tests/*/; do
  [ -d "$dir" ] && ls -1 "$dir" 2>/dev/null
done | sort -u | sed 's/.*/"  &",/' | head -20
echo "  ],"

# Cached datasets
echo "  \"cached_datasets\": ["
for dir in /data/cache/datasets /tmp/cache/datasets; do
  [ -d "$dir" ] && ls -1 "$dir" 2>/dev/null
done | sort -u | sed 's/.*/"  &",/' | head -20
echo "  ],"

# Who is using GPU
echo "  \"gpu_processes\": ["
rocm-smi --showpids 2>/dev/null | grep -E "^\s*[0-9]" | head -5 | sed 's/.*/"  &",/'
echo "  ]"

echo "}"
PROBE_SCRIPT
```

### 1.2 批量探测（默认只探测 Hot Nodes）

```bash
# 优先从 node_inventory.yaml 的 hot_nodes 提取（需 yq）
if [ -f ".cursor/configs/node_inventory.yaml" ]; then
  NODES=$(yq -r '.hot_nodes | keys[]' .cursor/configs/node_inventory.yaml)
else
  # 回退: 从 gpu_nodes.list 读取标注 [hot] 的节点
  NODES=$(grep '\[hot\]' .cursor/configs/gpu_nodes.list | awk '{print $1}')
  # 如果没有 [hot] 标注，取前 5 行
  [ -z "$NODES" ] && NODES=$(grep -v '^\s*#' .cursor/configs/gpu_nodes.list | grep -v '^\s*$' | head -5)
fi

for node in $NODES; do
  echo "=== Probing $node ==="
  bash scripts/probe-node.sh "$node" 2>/dev/null || echo "ERROR: $node unreachable"
done
```

如果 hot nodes 全部不可用，回退到 cold pool：

```bash
# Cold pool fallback
COLD_NODES=$(grep -v '^\s*#' .cursor/configs/gpu_nodes.list | grep -v '\[hot\]' | grep -v '^\s*$')
```

### 1.3 快速探测（只查 GPU 空闲 + 磁盘）

当只需快速筛选可用节点时，用精简版：

```bash
ssh -A -o ConnectTimeout=10 ${USER}@${NODE} \
  "echo '--- GPU ---'; rocm-smi --showuse 2>/dev/null | head -20; \
   echo '--- DISK ---'; df -h /tmp /data /home 2>/dev/null; \
   echo '--- PROCESSES ---'; rocm-smi --showpids 2>/dev/null | head -10"
```

---

## Layer 2: 亲和性调度

### 2.1 任务需求声明

每个 repo 测试任务声明所需资源：

```yaml
job:
  repo: video_to_world
  needs:
    models: [tinycudann, da3-depth]
    datasets: []
    min_disk_gb: 50
    min_gpu_mem_mb: 16000
    gpu_arch: gfx942
```

在 `experiments.md` 或 `plan-YYYYMMDD.md` 中自然描述即可，agent 解析后构建需求向量。

### 2.2 打分算法

```python
def score_node(node_info, job_needs, inventory_labels):
    """
    node_info: 探测结果 (JSON)
    job_needs: 任务需求
    inventory_labels: node_inventory.yaml 中的静态标签
    """
    score = 0.0

    # --- 数据亲和性 (权重最高) ---
    needed_models = set(job_needs.get("models", []))
    cached_models = set(node_info.get("cached_models", []))
    static_models = set(inventory_labels.get("models", []))
    all_models = cached_models | static_models
    model_hits = len(needed_models & all_models)
    score += model_hits * 10  # 每命中一个模型 +10

    needed_datasets = set(job_needs.get("datasets", []))
    cached_datasets = set(node_info.get("cached_datasets", []))
    static_datasets = set(inventory_labels.get("datasets", []))
    all_datasets = cached_datasets | static_datasets
    dataset_hits = len(needed_datasets & all_datasets)
    score += dataset_hits * 10  # 每命中一个数据集 +10

    # --- GPU 空闲度 ---
    gpu_free_ratio = node_info.get("gpu_free_mem_ratio", 0)
    score += gpu_free_ratio * 5  # 0~5 分

    gpu_idle = 1.0 - node_info.get("gpu_util_avg", 0) / 100.0
    score += gpu_idle * 3  # 0~3 分

    # --- 磁盘空间 ---
    disk_free_gb = node_info.get("disk_free_gb", 0)
    min_disk = job_needs.get("min_disk_gb", 50)
    if disk_free_gb < min_disk:
        score -= 100  # 硬约束：磁盘不足直接排除
    else:
        score += min(disk_free_gb / 100, 5)  # 0~5 分，上限 500G

    # --- 负载惩罚 ---
    active_processes = len(node_info.get("gpu_processes", []))
    score -= active_processes * 2  # 每个活跃进程 -2

    return score
```

### 2.3 节点选择流程

```
1. 读取 hot_nodes (top 5) → 候选节点列表
2. 并行探测候选节点 → 过滤不可达 / 磁盘不足的节点
3. 对每个可达节点计算 score
4. 按 score 降序排列
5. 贪心分配：最高分节点 → 第一个任务，次高 → 第二个，...
   - 同一节点可分配多个任务（串行执行），但每多一个任务 score 递减 -3
6. 如果 hot nodes 不够用 → 从 cold pool 补充探测
```

### 2.4 分配结果格式

```
=== Node Assignment (from top-5 hot nodes) ===
| Rank | Node     | Score | Assigned Repos           | Reason                           |
|------|----------|-------|--------------------------|----------------------------------|
| 1    | <node-1> | 28.5  | WoG, video_to_world      | wan2.1 cached (+10), 3.0T disk   |
| 2    | <node-2> | 21.0  | MotionCrafter, giga-brain | siglip cached (+10), 686G disk   |
| 3    | <node-3> | 8.0   | MV-SAM3D, DreamDojo      | no cache, clean node             |
```

---

## Layer 3: 存储治理

### 3.0 Docker 卷挂载规范（关键 — 必须在启动容器前确认）

> **原则：宿主机上只做只读探测；所有写操作（mkdir、下载模型/数据集、pip install）在容器内以 root 执行。**
>
> 共享节点上 `/data` 通常为 root 所有，普通用户无写权限。
> 容器默认以 root 运行，通过 `-v` 挂载后可直接写入宿主机目录，绕过权限问题。

#### 权限分工

| 操作 | 在哪里执行 | 原因 |
|------|-----------|------|
| 检测 DATA_DIR、扫描已有缓存 | **宿主机** (SSH user) | 只读，无权限问题 |
| `mkdir -p` 创建缓存目录 | **容器内** (root) | `/data` 可能无普通用户写权限 |
| 下载模型/数据集 | **容器内** (root) | 同上；且下载目标路径必须在 `-v` 挂载范围内 |
| pip install / 编译 | **容器内** (root) | 写入工作目录 |
| 清理临时文件 | **宿主机或容器** | 宿主机上清自己创建的；`/data` 下的用容器清 |

#### 标准 Docker 启动模板

```bash
# ===== Step 1: 宿主机上只读检测 DATA_DIR（不要硬编码 /data！） =====
if mountpoint -q /data 2>/dev/null; then DATA_DIR="/data"; else DATA_DIR="/tmp"; fi
CACHE_DIR="${DATA_DIR}/cache"
WORKDIR="${DATA_DIR}/overnight-tests"

# 注意：不在宿主机上 mkdir — 可能无写权限

# ===== Step 2: 启动容器（挂载 DATA_DIR） =====
docker run --rm \
  --device=/dev/kfd --device=/dev/dri \
  --ipc=host --security-opt seccomp=unconfined \
  -v ${DATA_DIR}:${DATA_DIR}              \
  -e DATA_DIR="${DATA_DIR}"               \
  -e HF_HOME="${CACHE_DIR}/huggingface"   \
  -e TORCH_HOME="${CACHE_DIR}/torch"      \
  -e MODEL_CACHE="${CACHE_DIR}/models"    \
  -w ${WORKDIR}                           \
  rocm/pytorch:rocm6.4.3_ubuntu24.04_py3.12_pytorch_release_2.6.0 \
  bash -c '
    # ===== Step 3: 容器内 root 创建目录 + 下载 =====
    mkdir -p ${DATA_DIR}/cache/{models,datasets,huggingface,torch}
    mkdir -p ${DATA_DIR}/overnight-tests/<repo_name>

    # 下载模型（容器内 root 有写权限）
    huggingface-cli download <model_id> --local-dir ${MODEL_CACHE}/<model_name>

    # 执行测试
    bash run.sh
  '
```

#### Agent Checklist（每次 `docker run` 前必须检查）

- [ ] **宿主机上只做只读操作**（检测 DATA_DIR、扫描缓存），不做 `mkdir` 或下载
- [ ] **`-v` 挂载了 DATA_DIR**（`-v ${DATA_DIR}:${DATA_DIR}`）
- [ ] **环境变量传入容器**（`DATA_DIR`, `HF_HOME`, `TORCH_HOME`, `MODEL_CACHE`）
- [ ] **容器内 root 创建目录 + 下载**（`mkdir -p` 和 `huggingface-cli download` 在容器内执行）
- [ ] 所有下载目标路径在 `-v` 挂载范围内（否则数据随 `--rm` 消失）

---

### 3.1 统一缓存目录

#### 存储拓扑（实测 2026-04-02）

节点存储拓扑是**异构的** — 并非所有节点都有独立 `/data` 挂载：

| 类型 | 特征 | 策略 |
|------|------|------|
| **Type A: 有独立 `/data` RAID** | `/dev/md127` 挂载到 `/data`，3.5-11T | `DATA_DIR=/data` |
| **Type B: 仅大 root 分区** | 无 `/data`，root `/` 1.8-3.5T | `DATA_DIR=/tmp` |

#### 自动检测脚本（在远端宿主机上执行 — 只读）

```bash
# detect-data-dir.sh — SSH 进入节点后首先运行（只读，无 mkdir）

if mountpoint -q /data 2>/dev/null; then
  DATA_DIR="/data"
elif [ -d /data ] && [ "$(df --output=fstype /data 2>/dev/null | tail -1)" != "$(df --output=fstype / 2>/dev/null | tail -1)" ]; then
  DATA_DIR="/data"
else
  DATA_DIR="/tmp"
fi

CACHE_ROOT="${DATA_DIR}/cache"
WORKDIR="${DATA_DIR}/overnight-tests"

# 只导出变量，不创建目录（可能无写权限）
export DATA_DIR CACHE_ROOT WORKDIR
export MODEL_CACHE="${CACHE_ROOT}/models"
export DATASET_CACHE="${CACHE_ROOT}/datasets"
export HF_HOME="${CACHE_ROOT}/huggingface"
export TORCH_HOME="${CACHE_ROOT}/torch"

# 报告检测结果 + 已有缓存
echo "DATA_DIR=${DATA_DIR} ($(df -h --output=avail ${DATA_DIR} 2>/dev/null | tail -1) free)"
echo "Writable by $(whoami): $([ -w "${DATA_DIR}" ] && echo 'YES' || echo 'NO — use container root')"
[ -d "${CACHE_ROOT}/models" ] && echo "Cached models: $(ls -1 ${CACHE_ROOT}/models/ 2>/dev/null | tr '\n' ', ')"
```

> **Agent 约定**:
> - 每次 SSH 到节点后，先运行上述检测确定 `DATA_DIR`
> - 禁止硬编码 `DATA_DIR=/data`
> - 检测脚本**只读不写** — `mkdir` 和下载在容器内 root 执行

#### 目录结构（宿主机上）

```
${DATA_DIR}/                    # /data (Type A) 或 /tmp (Type B)
├── cache/
│   ├── models/                 # 模型权重（持久化）
│   │   ├── sam2/
│   │   ├── dinov2/
│   │   ├── siglip/
│   │   ├── wan2.1/
│   │   └── da3-depth/
│   ├── datasets/               # 数据集（持久化）
│   │   ├── imagenet/
│   │   ├── coco/
│   │   └── scannet/
│   ├── huggingface/            # HF_HOME（持久化）
│   │   └── hub/
│   └── torch/                  # TORCH_HOME（持久化）
│       └── hub/
└── overnight-tests/            # 工作目录
    ├── <repo_1>/
    ├── <repo_2>/
    └── logs/
```

> **注意**: Type B 节点上 `/tmp` 在重启后会清空（tmpfs），模型缓存**非持久**。
> 对于需要持久缓存的 hot 节点，优先选择 Type A。

### 3.2 数据分级

| 级别 | 类型 | 策略 | 示例 |
|------|------|------|------|
| **Hot** (永久保留) | 基础模型权重 | 不清理 | sam2, sam3d, dinov2, siglip, wan2.1, da3-depth |
| **Warm** (LRU 7天) | Repo 专有 ckpts | 7 天未访问则清理 | hydra-ckpt, dreamworld-ckpt, openvla-7b |
| **Cold** (TTL 3天) | 构建产物/临时文件 | 3 天后自动清理 | .venv, pip cache, build/, __pycache__ |

### 3.3 散落数据发现 + Symlink 归档

公共节点上不同用户会把模型/数据集下载到各自目录。**在首次使用 hot node 或磁盘紧张时，先扫描再归档**，避免重复下载。

#### 发现脚本（在远端执行）

```bash
# discover-assets.sh — 扫描节点上散落的大模型和数据集
CACHE_ROOT="${1:-/data/cache}"

echo "=== Discovering model/dataset assets on $(hostname) ==="

# 扫描 safetensors / bin / pt / ckpt 等大模型文件 (>500MB)
echo ""
echo "--- Large model files (>500MB) ---"
find /home /tmp /data /mnt -type f \
  \( -name "*.safetensors" -o -name "*.pt" -o -name "*.pth" \
     -o -name "*.ckpt" -o -name "*.onnx" -o -name "*.msgpack" \) \
  -size +500M 2>/dev/null | while read f; do
  SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
  echo "  $SIZE  $f"
done | sort -rh

# 扫描所有 HuggingFace 缓存目录
echo ""
echo "--- HuggingFace cache directories ---"
find /home /tmp -maxdepth 4 -type d -name "huggingface" 2>/dev/null | while read hf_dir; do
  if [ -d "$hf_dir/hub" ]; then
    SIZE=$(du -sh "$hf_dir" 2>/dev/null | cut -f1)
    MODELS=$(ls -1 "$hf_dir/hub" 2>/dev/null | grep "^models--" | sed 's/^models--//; s/--/\//g')
    echo "  $SIZE  $hf_dir"
    echo "$MODELS" | sed 's/^/         /'
  fi
done

# 识别已知的基础模型（按关键词匹配）
echo ""
echo "--- Known foundation models found ---"
KNOWN_MODELS="sam2\|segment-anything-2\|dinov2\|siglip\|clip\|wan2\|depth-anything\|stable-diffusion\|llava\|whisper"
find /home /tmp /data -maxdepth 6 -type d 2>/dev/null | grep -i "$KNOWN_MODELS" | while read d; do
  SIZE=$(du -sh "$d" 2>/dev/null | cut -f1)
  echo "  $SIZE  $d"
done | sort -rh

echo ""
echo "=== Discovery Complete ==="
```

#### Symlink 归档流程

发现散落资产后，**symlink 到统一缓存目录**（不移动原文件，零风险）：

```bash
# 示例：发现 /home/alice/.cache/huggingface/hub/models--facebook--dinov2-base
# 归档到统一缓存
CACHE_ROOT="/data/cache"
SOURCE="/home/alice/.cache/huggingface/hub/models--facebook--dinov2-base"
TARGET="${CACHE_ROOT}/models/dinov2-base"

# 如果统一缓存里还没有，创建 symlink
if [ ! -e "$TARGET" ]; then
  ln -s "$SOURCE" "$TARGET"
  echo "LINKED: $SOURCE → $TARGET"
fi
```

**原则**：
- **只 symlink，不移动**：其他用户的文件不碰，尊重公共资源礼仪
- **发现重复时**：同一模型在多个用户目录都有？symlink 到最大/最完整的那个
- **权限检查**：`ls -la` 确认目标文件可读后再 link，避免 broken symlink
- 归档完成后自动更新 node_inventory labels

#### 什么时候执行

| 触发条件 | 动作 |
|---------|------|
| 首次将节点加入 hot nodes | 全量扫描 + 归档 |
| 磁盘 WARNING (<50G) | 扫描看是否有重复可以 deduplicate |
| overnight batch 完成后 | 轻量扫描（只查统一缓存目录） |
| 手动触发 | `bash discover-assets.sh` |

### 3.4 标签维护

每次 overnight 测试完成后或数据发现归档后，更新 hot nodes 的 labels：

```bash
# 对每个 hot node 探测统一缓存 + 已 symlink 的模型
for NODE in $HOT_NODES; do
  echo "=== $NODE ==="
  ssh -A ${USER}@${NODE} "ls -1 /data/cache/models/ /tmp/cache/models/ 2>/dev/null | sort -u"
done
# 将结果写回 node_inventory.yaml 的对应节点 labels.models
```

agent 在完成 overnight batch 或数据发现后，应自动执行此更新（仅 hot nodes）。

### 3.5 清理脚本

```bash
# cleanup-storage.sh — 在远端执行
CACHE_ROOT="${1:-/data/cache}"
WORKDIR="${2:-/tmp/overnight-tests}"

echo "=== Storage Cleanup Report ==="
echo "Before:"
df -h /tmp /data /home 2>/dev/null

# Cold: 删除 3 天以上的 build 产物
find "$WORKDIR" -maxdepth 2 -name ".venv" -mtime +3 -exec rm -rf {} + 2>/dev/null
find "$WORKDIR" -maxdepth 2 -name "build" -mtime +3 -exec rm -rf {} + 2>/dev/null
find "$WORKDIR" -maxdepth 2 -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Warm: 删除 7 天未访问的 repo 专有 ckpts
find "$CACHE_ROOT/models" -maxdepth 1 -mindepth 1 -atime +7 \
  ! -name "sam2" ! -name "sam3d" ! -name "dinov2" ! -name "siglip" \
  ! -name "wan2.1" ! -name "da3-depth" \
  -exec echo "REMOVE (warm, 7d): {}" \; \
  -exec rm -rf {} + 2>/dev/null

# pip cache
pip cache purge 2>/dev/null

echo "After:"
df -h /tmp /data /home 2>/dev/null
echo "=== Done ==="
```

### 3.5 Docker 容器清理

> **核心原则：公共节点上只清理容器 + dangling images（`<none>:<none>`），绝不删除有 tag 的镜像。**

```bash
# Step 1: 查看 Docker 整体占用（仅观察，不操作）
docker system df

# Step 2: 列出所有容器状态（决策依据）
echo "=== Running ==="
docker ps --format 'table {{.ID}}\t{{.CreatedAt}}\t{{.Status}}\t{{.Image}}'
echo "=== Exited / Dead ==="
docker ps -a --filter status=exited --filter status=dead \
  --format 'table {{.ID}}\t{{.CreatedAt}}\t{{.Status}}\t{{.Image}}'

# Step 3: 清理已停止 / 已死亡的容器（最安全）
docker container prune -f

# Step 4: 杀掉 running 但 >90 天的僵尸容器（排除 monitoring 类）
# 90 天阈值：公共节点上 3 个月前的容器几乎不可能还有人在用
docker ps --format '{{.ID}} {{.CreatedAt}} {{.Image}}' | while read CID DATE TIME TZ IMG; do
  # 跳过 monitoring / infra 容器
  echo "$IMG" | grep -qiE 'node-exporter|prometheus|grafana|cadvisor' && continue
  DAYS=$(( ($(date +%s) - $(date -d "$DATE $TIME" +%s)) / 86400 ))
  [ "$DAYS" -gt 90 ] && echo "ZOMBIE (${DAYS}d): $CID $IMG" && docker stop $CID && docker rm $CID
done

# Step 5: 清理悬空镜像 — 仅删除 <none>:<none> 的 dangling images（安全）
# 注意：不带 -a！带 -a 会删所有未关联容器的镜像，绝对禁止
docker image prune -f

# Step 6: 清理 build cache（安全，不影响镜像和容器）
docker builder prune -f
```

**允许清理的镜像类型**：

仅限 **dangling images**（`<none>:<none>`），即无 tag 的悬空镜像：
- build 中间层残余
- 被同 tag 新版本覆盖后留下的旧层
- 命令：`docker image prune -f`（**不带 `-a`**）

```bash
# 查看有多少 dangling images
docker images -f dangling=true
# 清理
docker image prune -f
```

**禁止的操作**（在公共节点上绝不执行）：

| 命令 | 为什么禁止 |
|------|-----------|
| `docker image prune -a -f` | `-a` 会删除所有未关联容器的有 tag 镜像，其他用户需重新 pull |
| `docker system prune -a -f` | 上面的超集，连 volume 也会清 |
| `docker image rm <tag/id>` | 除非明确是自己创建的临时镜像 |

在探测脚本 (`probe-node.sh`) 中已加入 Docker 占用检查 + 僵尸容器计数。

### 3.6 磁盘告警

探测时如果磁盘剩余 < 阈值，自动标记：

```
if disk_free_gb < 20:
    status = "CRITICAL — 不可分配任务，建议先执行 cleanup-storage.sh + docker system prune"
elif disk_free_gb < 50:
    status = "WARNING — 仅分配轻量任务，建议清理 cold 数据"
else:
    status = "OK"
```

---

## 完整工作流（与其他 Skill 协作）

```
┌─────────────────────────────────────────────────┐
│  cursor-overnight-task-manager                  │
│  Phase 0: 委托 gpu-cluster-resource-manager     │
│           ↓                                     │
│  ┌─────────────────────────────────────┐        │
│  │ gpu-cluster-resource-manager        │        │
│  │ 1. 读取 hot_nodes (top 5)           │        │
│  │ 2. 并行探测 hot nodes               │        │
│  │ 3. 解析任务需求                     │        │
│  │ 4. 亲和性打分                       │        │
│  │ 5. 输出节点分配方案                 │        │
│  │ 6. (可选) 存储清理                  │        │
│  └─────────────────────────────────────┘        │
│           ↓                                     │
│  Phase 1-7: 按分配方案执行测试                   │
│  Phase 完成后: 更新 hot_nodes labels             │
│                                                 │
│  remote-ssh-github-auto → SSH 连接层            │
│  experiment-driven-doc  → 实验文档              │
│  agent-heartbeat        → 长任务心跳            │
└─────────────────────────────────────────────────┘
```

---

## 与其他 Skill 的协作

| Skill | 关系 |
|-------|------|
| **cursor-overnight-task-manager** | Phase 0 委托本 skill 做节点选择；Phase 6 完成后调用本 skill 更新标签 |
| **remote-ssh-github-auto** | SSH 连接层；本 skill 的探测脚本依赖 SSH Agent Forwarding |
| **experiment-driven-doc** | experiments.md 中的"节点选择"和"已知风险"参考本 skill 的亲和性分析 |
| **agent-heartbeat** | 探测多节点时启用心跳（>60s） |
