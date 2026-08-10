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

探测 → 打分 → 选节点 → 管存储。**30+ 节点的池子里只精细维护 top 5 hot nodes**（标签 + 缓存 + 定期清理）；
cold pool 只在 hot 全部不可用（磁盘满 / GPU 被占 / SSH 不通）时探测回退。

## 配置

首选 `.cursor/configs/node_inventory.yaml`（已 gitignore）；缺失则退回 `.cursor/configs/gpu_nodes.list`
（每行一个 SSH 主机名，`# [hot]` 标注热节点，无标注则取前 5 行）。

```yaml
defaults:
  user: <username>
  cache_root: /data/cache        # 无独立 /data 的节点回退 /tmp
  workdir: /tmp/overnight-tests
  hot_models: [sam2, dinov2, siglip, wan2.1, da3-depth]   # 永不清理

hot_nodes:
  <node-1>:
    gpu_type: MI300X
    gpu_count: 8
    arch: gfx942
    storage_type: A              # A = 独立 /data RAID；B = 仅大 root，data_dir 回退 /tmp
    data_dir: /data
    labels: {models: [siglip], datasets: []}
    notes: "root 分区 98%，只用 /data"
```

每次 overnight batch 或资产归档完成后，把新出现的缓存写回对应节点的 `labels.models`。

---

## Layer 1 — 探测

`ssh -A -o ConnectTimeout=10` 到每个 hot node，采集五项：

- GPU 空闲显存与利用率 —— `rocm-smi --showmeminfo vram --showuse`
- 占用进程 —— `rocm-smi --showpids`
- `/tmp /data /home /` 剩余 —— `df -BG`
- `/data` 是否独立挂载 —— `mountpoint -q /data`（决定 `DATA_DIR`）
- 统一缓存里已有的 models / datasets —— `ls ${DATA_DIR}/cache/{models,datasets}`

顺带记一下 `docker system df` 与僵尸容器数。hot nodes 全部不可达或磁盘不足时，才从 cold pool 补探。

## Layer 2 — 亲和性打分

任务需求在 `experiments.md` / `plan-*.md` 里自然描述即可（需要哪些 model/dataset、`min_disk_gb`、
`min_gpu_mem_mb`、`gpu_arch`），agent 解析成需求向量后打分：

| 项 | 分 |
|---|---|
| 每命中一个所需 model / dataset（探测缓存 ∪ 静态标签） | **+10** |
| GPU 空闲显存比例 | ×5 |
| GPU 空闲度（1 − util） | ×3 |
| 磁盘余量 | +min(free_gb / 100, 5) |
| 每个活跃 GPU 进程 | −2 |
| 同一节点每多分配一个任务（可串行复用） | −3 |
| **磁盘 < `min_disk_gb`** | **−100，硬排除** |

按分降序贪心分配，输出 `| Rank | Node | Score | Assigned Repos | Reason |`。

---

## Layer 3 — 存储治理

### 写操作一律在容器内做

**共享节点的 `/data` 通常属 root，普通用户没有写权限；容器默认以 root 跑，`-v` 挂载后可直接写宿主机目录。**

- **宿主机只读**：检测 `DATA_DIR`、扫描已有缓存。**不要在宿主机 `mkdir` 或下载。**
- **容器内 root 写**：`mkdir -p`、下载模型/数据集、pip install、编译。

`DATA_DIR` 必须检测、不能硬编码。Type B 节点（无独立 `/data`）的 `/tmp` 重启即清空，
需要持久缓存就挑 Type A。

```bash
mountpoint -q /data && DATA_DIR=/data || DATA_DIR=/tmp
docker run --rm --device=/dev/kfd --device=/dev/dri \
  --ipc=host --security-opt seccomp=unconfined \
  -v ${DATA_DIR}:${DATA_DIR} -e DATA_DIR=${DATA_DIR} \
  -e HF_HOME=${DATA_DIR}/cache/huggingface \
  -e TORCH_HOME=${DATA_DIR}/cache/torch \
  -e MODEL_CACHE=${DATA_DIR}/cache/models \
  -w ${DATA_DIR}/overnight-tests <image> bash -c '
    mkdir -p ${DATA_DIR}/cache/{models,datasets,huggingface,torch}
    huggingface-cli download <model_id> --local-dir ${MODEL_CACHE}/<name>
    bash run.sh'
```

四个必查项：`-v` 挂了 `DATA_DIR`／四个缓存环境变量都传进去了／`mkdir` 和下载在容器内／
**所有下载路径落在挂载范围内**（否则随 `--rm` 一起消失）。

目录约定：`${DATA_DIR}/cache/{models,datasets,huggingface,torch}` +
`${DATA_DIR}/overnight-tests/<repo>`，日志在 `overnight-tests/logs/`。

### 数据分级与清理

| 级别 | 内容 | 策略 |
|---|---|---|
| **Hot** | `hot_models` 里的基础模型 | 不清理 |
| **Warm** | repo 专有 ckpt | `-atime +7` 清理 |
| **Cold** | `.venv` / `build` / `__pycache__` / pip cache | `-mtime +3` 清理 |

清理脚本就是按这三档跑 `find … -exec rm -rf {} +`，Warm 那档要 `! -name` 排除 `hot_models`；
跑前跑后各打一次 `df -h`。

### 散落资产：只 symlink，不移动

公共节点上别的用户会把模型下到各自目录。**首次把节点纳入 hot、或磁盘告警时先扫描再归档，避免重复下载**：
`find /home /tmp /data -size +500M \( -name '*.safetensors' -o -name '*.pt' -o -name '*.ckpt' \)`，
外加各处 `huggingface/hub` 下的 `models--*`。

发现后 `ln -s <source> ${CACHE_ROOT}/models/<name>`：**不移动别人的文件**（公共资源礼仪）；
同一模型有多份就 link 最完整的那份；link 前 `ls -la` 确认可读，避免 broken symlink；
归档完更新 inventory labels。

### Docker 清理：只碰容器和悬空镜像

```bash
docker system df            # 先看占用
docker container prune -f   # 已停止容器，最安全
docker image prune -f       # 仅 dangling <none>:<none>
docker builder prune -f     # build cache
```

running 但 > 90 天的僵尸容器可以 stop + rm（三个月前的容器几乎不可能还有人用），
但要跳过 `node-exporter|prometheus|grafana|cadvisor` 这类 infra 容器。

**公共节点上绝对禁止**：`docker image prune -a`（会删掉所有有 tag 但未关联容器的镜像，别人得重 pull）、
`docker system prune -a`（前者的超集，连 volume 都清）、`docker image rm <tag>`（除非确认是自己建的临时镜像）。

### 磁盘告警

`< 20G` **CRITICAL**，不分配任务，先清理；`< 50G` **WARNING**，只分配轻量任务；其余 OK。

---

## 与其他 Skill 的协作

| Skill | 关系 |
|---|---|
| **cursor-overnight-task-manager** | Phase 0 委托本 skill 选节点；batch 完成后回来更新标签 |
| **remote-ssh-github-auto** | SSH 连接层，探测依赖 Agent Forwarding |
| **tmux-remote-detach** | 选中节点后在其上创建 tmux session |
| **experiment-driven-doc** | experiments.md 的「节点选择」「已知风险」引用本 skill 的分析 |
| **agent-heartbeat** | 多节点探测 > 60s 时输出心跳 |
