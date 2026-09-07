---
name: local-push-remote-pull-test
version: 1.0.0
author: ZJLi2013
description: 本地开发后推送到 GitHub，再登录远端拉取并执行测试的通用工作流。用于"本地改代码+git push+远端 git pull+远端测试"场景，并包含远端本地改动导致 pull 失败时的 stash 处理。
disable-model-invocation: true
allowed-tools: [Shell]
---

# 本地 Push + 远端 Pull/Test（通用版）

## 适用场景

- 本地完成代码修改，需要同步到远端节点验证
- 需要固定流程：本地 `git push` -> 远端 `git pull --ff-only` -> 远端跑测试
- 远端存在历史改动，可能导致 `pull` 冲突或覆盖风险

## 标准工作流（默认执行）

### Step 1：本地提交与推送

```bash
cd <local_repo_dir>
git status --short --branch
git add <changed_files_or_dot>
git commit -m "<message>"
git push origin <branch>
```

### Step 2：远端拉取最新代码

```bash
ssh <user>@<host> "cd <remote_repo_dir> && git status --short --branch && git pull --ff-only"
```

### Step 3：远端执行验证测试

```bash
ssh <user>@<host> "cd <remote_repo_dir> && <test_command>"
```

常见示例：

```bash
# Python unittest
ssh <user>@<host> "cd <remote_repo_dir> && PYTHONPATH=./src python3 -m unittest tests/test_xxx.py"

# Pytest
ssh <user>@<host> "cd <remote_repo_dir> && PYTHONPATH=./src pytest -q tests/test_xxx.py"
```

### Step 4：回传结果

- 明确给出：push 成功/失败、pull 成功/失败、测试通过/失败
- 若失败，附关键错误摘要

---

## 故障分支：远端有本地改动导致 pull 失败

当 `git pull --ff-only` 报 "would be overwritten by merge"：

```bash
cd <remote_repo_dir>
git status --short --branch
git stash push -u -m "pre-pull-backup-<date>"
git pull --ff-only
git stash list
```

若需要恢复 stash：

```bash
git stash pop
```

若 `stash pop` 冲突，先问用户保留哪一边，再执行：

```bash
# 保留当前分支（通常是最新 main）
git restore --source=HEAD --staged --worktree <conflict_files>

# 保留 stash 版本（需用户明确同意）
git checkout --theirs <conflict_files>
git add <conflict_files>
```

---

## 参数模板（跨项目复用）

- `<local_repo_dir>`：本地仓库路径
- `<remote_repo_dir>`：远端仓库路径
- `<branch>`：目标分支（如 `main`）
- `<test_command>`：远端测试命令（按项目替换）

## 节点清单

多节点批量执行时，从共享配置文件读取目标节点：

- 路径：`.cursor/configs/gpu_nodes.list`（项目级，与其他 skill 共享，git-ignored）
- 首次使用：`cp .cursor/configs/gpu_nodes.list.example .cursor/configs/gpu_nodes.list`

```bash
nodes=$(grep -v '^\s*#' .cursor/configs/gpu_nodes.list | grep -v '^\s*$')
for host in $nodes; do
  ssh <user>@$host "cd <remote_repo_dir> && git pull --ff-only && <test_command>"
done
```
