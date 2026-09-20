# Remote Exec — Reference

主流程见 [SKILL.md](SKILL.md)。本文只放两类不常用但要精确的东西：inventory 字段、批量夜测流程。

## node_inventory.yaml 字段

```yaml
defaults:
  user: <username>
  cache_root: /data/cache        # 无独立 /data 的节点回退 /tmp
  workdir: /tmp/overnight-tests
  hot_models: [sam2, dinov2, siglip]   # Hot 档，永不清理

hot_nodes:
  <node-1>:
    gpu_type: MI300X
    gpu_count: 8
    arch: gfx942                 # 对齐 HSA_OVERRIDE_GFX_VERSION
    storage_type: A              # A = 独立 /data RAID；B = 仅大 root，data_dir 回退 /tmp
    data_dir: /data
    labels: {models: [siglip], datasets: []}   # 探测到新缓存后写回这里
    notes: "root 分区 98%，只用 /data"
```

每次 batch 或资产归档完成后，把新出现的缓存写回对应节点的 `labels.models`。

## 多节点 / 多卡排布

三种，按共享显存的需要选：

- **单节点串行**（默认，显存不打架）：session 内 `for s in tasks/*.sh; do bash $s; done`
- **单节点并行**：每个任务一个 session，各自 `export HIP_VISIBLE_DEVICES=<i>`
- **跨节点**：先 `scp` 任务脚本，再对每个节点建一个 session

次日收集：对每个节点 `tmux ls` + `tail -5 logs/*.log`。

## 批量夜测开源 repo

`remote-exec` 的一个具体应用：一晚上把一批 GitHub repo 在 ROCm 上跑通。
脚本 `scripts/overnight-runner.sh`（配 `scripts/analyze-results.py` 出报告）。

**输入** `input-list.txt`，每行 `<github_url> [branch] [run_command]`，`#` 与空行跳过：

```
https://github.com/facebookresearch/detectron2  main
https://github.com/huggingface/transformers  main  "python examples/.../run_glue.py --do_eval"
https://github.com/openai/whisper
```

只给 URL 就自动探测测试命令；给了 `run_command` 就直接用，不再探测。

**先决条件**：远端 `rocminfo` 可用、Python 3.8+、git、磁盘够。预检失败就停下报告，不硬跑。

**流程**：选节点（见 SKILL.md 第 2 节，磁盘 < 20G 硬排除）→ 远端 clone 或
`git fetch && checkout && pull --ff-only` → 依赖 → 数据 → tmux 里 headless 跑 → 回传出报告。

依赖按优先级装：`requirements.txt` → `setup.py`/`pyproject.toml`（先试
`pip install -e ".[dev,test]"`，失败退 `-e .`）→ `environment.yml`。装完确认是 ROCm 版 torch
（`torch.version.hip` 非空）。

数据优先跑 repo 自带的 `scripts/download_data.sh` / `download.py` / `data/download.sh`。
**README 里的 Google Drive 链接标记为需人工处理，不要卡在那里。**

测试命令探测优先级：清单里指定 → `make test`（Makefile 有 `^test:`）→
`pytest tests/ -x -v --timeout=600`（有 `pytest.ini`/`setup.cfg`/`tests/`）→
`examples/*.py --help` 冒烟 → 报 `NO_AUTO_DETECT` 要求在清单里写明。

运行环境：`timeout 7200` 兜底，输出 `tee` 到 `$LOGDIR/run_<ts>.log`，结尾追加 `EXIT_CODE`
与 `rocm-smi` 快照。

**报告**：`./overnight-results/<date>/` 下一张
`| Repo | Node | Status | Duration | Key Metric |` 总表，每个 repo 附命令、exit code、日志尾、
GPU 峰值显存、错误，末尾列 Next Steps。

**收尾**：把新下载的 models/datasets 写回 `node_inventory.yaml` 的 labels。

## 测出兼容性修复之后

要提上游时走 `upstream-contribute`（PR-vs-Issue 判断与 body 模板）与
`external-output-boundary` rule（AI 披露、GPU 型号脱敏、私料清单）。这里只留三个易踩点：

- GitHub fork API 是**异步的**，创建后要轮询 `GET /repos/<you>/<repo>` 到 200 再 clone。
- 本地保留 `upstream` 与 `myfork` 两个 remote，PR 分支从 `upstream/main` 切。
- **实验记录（`experiments.md`、`overnight-results/`）不进 PR 分支。**
