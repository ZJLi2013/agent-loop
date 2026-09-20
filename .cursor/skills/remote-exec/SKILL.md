---
name: remote-exec
description: >-
  在远端 GPU 节点上跑东西并让它活下来：SSH 与认证、选节点、tmux 保活、容器内写缓存与磁盘治理，
  外加一张远端失败的自修表（改什么、重试几次、什么时候换节点）。
  Use when running anything on a remote GPU node, or when a remote run fails.
disable-model-invocation: true
allowed-tools: [Shell]
---

# Remote Exec

**边界**：本 skill 只管「活儿怎么上去、怎么活下来、失败了怎么自己修」。跑什么、为什么跑、
结果算不算通过，归 `task-state` 与 `experiment-design`。

## 四条硬规则

1. **SSH 连接不承载长任务**。长任务一律 detach（tmux 或 `docker run -d`），本地只发短命令轮询。
2. **输出 `tee` 到日志文件**。tmux 滚动缓冲会溢出，日志不会。
3. **宿主机只读，写操作在容器内做**。共享节点的 `/data` 属 root，普通用户没有写权限。
4. **10 秒不返回就视为不可用**，换连接方式，不继续等。

## 配置

首选 `.cursor/configs/node_inventory.yaml`（gitignored，模板见同目录 `.example`）；
缺失则退回 `.cursor/configs/gpu_nodes.list`（每行一个 SSH host，`# [hot]` 标热节点，无标注取前 5 行）。

30+ 节点的池子里**只精细维护 top 5 hot nodes**（标签 + 缓存 + 定期清理）；cold pool 只在
hot 全部不可用时探测回退。字段含义与完整样例见 [reference.md](reference.md)。

## 1. 连上去

普通 Linux 节点用 OpenSSH，显式指定 user 与 key：

```powershell
ssh -o BatchMode=yes -o ForwardAgent=no -i "<key_path>" <user>@<host> "hostname; whoami"
```

**卡在 publickey/auth 阶段就换 Paramiko runner**（`scripts/ssh_paramiko.py`，支持 `--retries`），
不要试 ControlMaster / ControlPath / socket 预热——在 Windows OpenSSH + Conductor 节点上这些都不work。
换过去之后该节点的后续短命令都走 runner，别来回切。

GitHub 认证用 agent forwarding，**只用于远端访问 GitHub，不用于修节点登录**：
本地 `ssh-add <key>` → `ssh -A <user>@<host>` → 远端 `ssh -T git@github.com` 验证 → `git pull --ff-only`。

## 2. 选节点

`ssh -o ConnectTimeout=10` 到每个 hot node 采集五项：GPU 空闲显存与利用率
（`rocm-smi --showmeminfo vram --showuse`）、占用进程（`--showpids`）、`/tmp /data /home /` 剩余
（`df -BG`）、`/data` 是否独立挂载（`mountpoint -q /data`，决定 `DATA_DIR`）、统一缓存里已有的
models/datasets。顺带记 `docker system df` 与僵尸容器数。

任务需求（需要哪些 model/dataset、`min_disk_gb`、`min_gpu_mem_mb`、`gpu_arch`）在实验文档里
自然描述即可，解析成需求向量后打分：

| 项 | 分 |
|---|---|
| 每命中一个所需 model / dataset（探测缓存 ∪ 静态标签） | **+10** |
| GPU 空闲显存比例 | ×5 |
| GPU 空闲度（1 − util） | ×3 |
| 磁盘余量 | +min(free_gb / 100, 5) |
| 每个活跃 GPU 进程 | −2 |
| 同一节点每多分配一个任务（可串行复用） | −3 |
| **磁盘 < `min_disk_gb`** | **−100，硬排除** |

按分降序贪心分配，输出 `| Rank | Node | Score | Assigned | Reason |`。
磁盘 `< 20G` 不分配任务先清理，`< 50G` 只分配轻量任务。

## 3. 让它活下来

session 名统一 `<repo>-<日期>`，`exec bash` 让任务结束后 session 不消失：

```bash
NODE="user@gpu-node"; SESSION="myrepo-$(date +%Y%m%d-%H%M)"; LOG="/tmp/overnight-tests/logs/$SESSION.log"
ssh -A $NODE "tmux new-session -d -s $SESSION \
  'mkdir -p $(dirname $LOG) && bash /tmp/overnight-tests/run_task.sh 2>&1 | tee $LOG; \
   echo \"=== END \$(date) EXIT=\$? ===\" | tee -a $LOG; exec bash'"
```

| 目的 | 命令 |
|---|---|
| 列 session | `tmux ls` |
| 看日志尾（不 attach） | `tail -30 $LOG` |
| 看当前屏幕 | `tmux capture-pane -t $SESSION -p \| tail -20` |
| 进去交互 | `ssh -A -t $NODE "tmux attach -t $SESSION"` |
| 收工 | `tmux kill-session -t $SESSION` |

容器化任务用 `docker run -d --name <job>` 替代 tmux，轮询 `docker logs --tail 80 <job>` 与
`docker inspect -f '{{.State.ExitCode}}' <job>`。多节点/多卡排布见 [reference.md](reference.md)。

## 4. 写数据

`DATA_DIR` **必须检测、不能硬编码**。Type B 节点（无独立 `/data`）的 `/tmp` 重启即清空，
需要持久缓存就挑 Type A。

```bash
mountpoint -q /data && DATA_DIR=/data || DATA_DIR=/tmp
docker run --rm --device=/dev/kfd --device=/dev/dri \
  --ipc=host --security-opt seccomp=unconfined \
  -v ${DATA_DIR}:${DATA_DIR} -e DATA_DIR=${DATA_DIR} \
  -e HF_HOME=${DATA_DIR}/cache/huggingface -e TORCH_HOME=${DATA_DIR}/cache/torch \
  -e MODEL_CACHE=${DATA_DIR}/cache/models \
  -w ${DATA_DIR}/overnight-tests <image> bash -c 'mkdir -p ${DATA_DIR}/cache/{models,datasets}; bash run.sh'
```

四个必查项：`-v` 挂了 `DATA_DIR`／四个缓存环境变量都传进去了／`mkdir` 和下载在容器内／
**所有下载路径落在挂载范围内**（否则随 `--rm` 一起消失）。

目录约定 `${DATA_DIR}/cache/{models,datasets,huggingface,torch}` +
`${DATA_DIR}/overnight-tests/<repo>`，日志在 `overnight-tests/logs/`。

## 5. 存储治理

三档清理：**Hot**（inventory 里 `hot_models` 的基础模型）不清理；**Warm**（repo 专有 ckpt）
`-atime +7`，清理时要 `! -name` 排除 hot；**Cold**（`.venv` / `build` / `__pycache__` / pip cache）
`-mtime +3`。跑前跑后各打一次 `df -h`。

**散落资产只 symlink 不移动**（公共资源礼仪）。首次纳入 hot 或磁盘告警时先扫再归档，避免重复下载：
`find /home /tmp /data -size +500M \( -name '*.safetensors' -o -name '*.pt' -o -name '*.ckpt' \)`
外加各处 `huggingface/hub` 下的 `models--*`。同一模型多份就 link 最完整的，link 前 `ls -la`
确认可读，归档完更新 inventory labels。

**Docker 只碰容器和悬空镜像**：`container prune -f` / `image prune -f` / `builder prune -f`。
running 但 > 90 天的僵尸容器可以 stop + rm，跳过 `node-exporter|prometheus|grafana|cadvisor`。
**公共节点上绝对禁止** `docker image prune -a`、`docker system prune -a`、`docker image rm <tag>`——
前两个会删掉别人得重 pull 的镜像。

## 失败处置表

**远端失败绝大多数是环境问题，不是结论。** 下表左三类自己修，右两类才上报。
重试次数用尽后才升级为 blocker，并带上已试过哪几条。

| 失败 | 处置 | 上限 |
|---|---|---|
| `git pull --ff-only` 报 would be overwritten | `git stash push -u -m pre-pull-<date>` 再 pull，**不 drop stash** | 1 |
| Paramiko `Authentication timeout` | 同一 runner 加 `--retries 2`，不切回 OpenSSH | 2 |
| `hipErrorNoBinaryForGpu` | `HSA_OVERRIDE_GFX_VERSION` 对齐 `rocminfo` 实际架构 | 1 |
| `HIP out of memory` | `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True`，再减半 batch | 2 |
| `torch.cuda.is_available()` False | 确认 `rocminfo` 有输出 + torch 是 ROCm 版（`torch.version.hip`） | 1 |
| NCCL/RCCL 多卡挂死 | `NCCL_P2P_DISABLE=1` | 1 |
| 磁盘 < 20G | 跑 Cold 档清理后重试；仍不足则换节点 | 1 |
| 节点 10s 不返回 | 换 Paramiko runner；仍不通则标记 down 换节点 | 1 |
| `stash pop` 冲突 | **停下问人**保留哪一边 | — |
| 任务本身的指标/断言失败 | **不是本 skill 的事**，交回实验文档当结果处理 | — |

## 两个坑

**PowerShell 引号嵌套几乎必翻车**：复杂命令一律写成 `.sh` 脚本 `scp` 上去，tmux 里只 `bash script.sh`。

**`ssh -A` 的 agent socket 在 SSH 断开后失效**，tmux 里后续的 `git pull` 会挂。把所有
`git clone/pull` 放在脚本开头、SSH 还连着的时候做完。

## 相关

- `task-state`：把 session 名、日志路径、恢复命令写进交接笔记，跨 session 接手靠它不靠本 skill。
- `agent-heartbeat`：轮询 `capture-pane` / `tail log` 时输出心跳与进度。
- `upstream-contribute`：远端测出的兼容性修复要提 PR 时，body 生成与 GPU 型号脱敏走它。
- 批量夜间测多个 repo 的具体流程见 [reference.md](reference.md)。
