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
disable-model-invocation: true
allowed-tools: [Shell]
---

# Cursor Overnight Task Manager

批量挂任务过夜：读 repo 列表 → 选节点 → clone → setup → headless run → 收结果 → 出报告。

**边界**：本 skill 管批量执行本身；`long-running-agent-harness` 管外层的任务拆解、runbook、
进度日志与交接。overnight run 若是更大任务的一环，先用 harness 建 `.cursor/harness/`。

**先决条件**：本机能 SSH 到远端（推荐 Agent Forwarding，见 `remote-ssh-github-auto`）；
远端有 ROCm 运行时（`rocminfo` 可用）、Python 3.8+、git、足够磁盘。

## 输入

`input-list.txt` 每行 `<github_url> [branch] [run_command]`，`#` 与空行跳过：

```
https://github.com/facebookresearch/detectron2  main
https://github.com/huggingface/transformers  main  "python examples/.../run_glue.py --do_eval"
https://github.com/openai/whisper
```

只给 URL 就自动检测测试命令；给了 `run_command` 就直接用它，不再检测。
节点配置见 `gpu-cluster-resource-manager`（`node_inventory.yaml`，回退 `gpu_nodes.list`）。

---

## 工作流

### Phase 0 — 选节点

**委托 `gpu-cluster-resource-manager`**：探测 hot nodes → 解析本批 repo 需要哪些 models/datasets →
亲和性打分 → 输出分配方案。磁盘 < 20G 硬排除，< 50G 只给轻量任务。**预检失败就停下报告**，不要硬跑。

### Phase 1–2 — 解析清单并在远端 clone

逐行 parse 出 `repo_url / branch / run_cmd`。远端在 `$WORKDIR/<repo>` 下：已存在就
`git fetch && git checkout <branch> && git pull --ff-only`，否则 `git clone` 后 checkout。

### Phase 3 — 依赖

`python3 -m venv .venv --system-site-packages` 后按优先级装：
`requirements.txt` → `setup.py`/`pyproject.toml`（先试 `pip install -e ".[dev,test]"`，失败退 `-e .`）
→ `environment.yml`。装完确认 ROCm 版 torch：`python3 -c "import torch; print(torch.version.hip)"`。

### Phase 4 — 数据与权重

优先跑 repo 自带的 `scripts/download_data.sh` / `download.py` / `data/download.sh`。
HuggingFace 模型首次运行会自动下载（确保 `HF_HOME` 指向统一缓存）。
README 里的 Google Drive 链接标记为**需人工处理**，不要卡在那里。

### Phase 5 — Headless 运行

跑在 tmux 里（见 `tmux-remote-detach`），输出 tee 到 `$LOGDIR/run_<ts>.log`，`timeout 7200` 兜底，
结尾追加 `EXIT_CODE` 和 `rocm-smi` 快照。

```bash
export HIP_VISIBLE_DEVICES=0
export HSA_OVERRIDE_GFX_VERSION=11.0.0        # 按实际 GPU 架构调整
export PYTORCH_HIP_ALLOC_CONF=expandable_segments:True
```

命令检测优先级：`run_command` 指定 → `make test`（Makefile 里有 `^test:`）→
`pytest tests/ -x -v --timeout=600`（有 `pytest.ini`/`setup.cfg`/`tests/`）→
`examples/*.py --help` 冒烟 → 报 `NO_AUTO_DETECT` 要求在清单里写明命令。

### Phase 6 — 回传与分析

`scp` 远端 `logs/` 到 `./overnight-results/<date>/<node>/`，生成 `report.md`：
一张 `| Repo | Node | Status | Duration | Key Metric |` 总表，每个 repo 附命令、exit code、
日志尾部、GPU 峰值显存、遇到的错误，末尾列 Next Steps。

### Phase 7 — 回馈上游（可选）

测出 ROCm 兼容性修复时才做，**body 生成与 GPU 型号脱敏走 `upstream-contribute`**。
这里只留三个容易踩的点：GitHub fork API 是**异步的**，创建后要轮询
`GET /repos/<you>/<repo>` 到 200 再 clone；本地保留 `upstream` 与 `myfork` 两个 remote，
PR 分支从 `upstream/main` 切；**实验记录（`experiments.md`、`overnight-results/`）不进 PR 分支**。

### 收尾

batch 完成后调 `gpu-cluster-resource-manager` 的探测，把新下载的 models/datasets
写回 `node_inventory.yaml` 的 labels。

---

## AMD GPU 常见问题

| 问题 | 解法 |
|---|---|
| `hipErrorNoBinaryForGpu` | `HSA_OVERRIDE_GFX_VERSION` 对齐实际架构 |
| `HIP out of memory` | 减 batch_size，或 `PYTORCH_HIP_ALLOC_CONF=expandable_segments:True` |
| NCCL 多卡挂死 | `NCCL_P2P_DISABLE=1`，或升级 ROCm RCCL |
| `torch.cuda.is_available()` 为 False | 确认 `rocminfo` 有输出且 torch 是 ROCm 版 |
| 算子不支持 | `CUDA_VISIBLE_DEVICES=""` 跑 CPU 基线做对比 |

## 与其他 Skill 的协作

- **gpu-cluster-resource-manager**：Phase 0 选节点 + 存储治理；收尾更新标签
- **tmux-remote-detach**：Phase 5 的进程托管，本地可断开
- **remote-ssh-github-auto**：SSH 与 GitHub 认证
- **rocm-lib-compat**：flash-attn / triton / aiter 等的 ROCm 替换（Phase 3）
- **upstream-contribute**：Phase 7 的 PR/Issue body 与脱敏
- **experiment-driven-doc** / **long-running-agent-harness** / **agent-heartbeat**：实验文档 / 外层编排 / 长任务心跳
