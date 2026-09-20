# my_skills

个人 Agent Skills 库，面向 **Cursor** 的可复用工作流集合。部分高风险/长任务 Skills 默认不自动启用，需显式点名调用。

---

## 目录结构

```
my_skills/
├── .cursor/
│   ├── skills/                          # Cursor Agent Skills
│   │   ├── feature-dev-pipeline/        # 大 feature 拆子任务（自动）
│   │   ├── experiment-driven-doc/       # 实验两道门 + 记录模板（自动）
│   │   ├── task-loop/                   # task.md、验收检查点、交接（自动）
│   │   ├── agent-heartbeat/             # 长任务心跳（自动）
│   │   ├── remote-exec/                 # 远端 GPU 执行、存活、自修、存储
│   │   ├── code-review/                 # PR/diff 评审的四段输出
│   │   ├── code-to-kernel-diagram/      # 模块源码 → kernel 数据流图
│   │   ├── upstream-contribute/         # 实验后评估上游贡献
│   │   └── research-to-blog/            # 文献调研 → 自媒体
│   ├── rules/                           # always-applied 约束
│   └── configs/                         # 本地私有配置（git-ignored）
│       ├── node_inventory.yaml          # 节点清单（用户自建）
│       └── node_inventory.yaml.example  # 模板
└── .gitignore
```

---

## Skills 列表

| skill | 启用方式 | 描述 |
|-------|----------|------|
| `feature-dev-pipeline` | 自动触发 | 大 feature → 子任务 → 设计 → 实现+实验 → 回填 |
| `task-loop` | 自动触发 | `task.md` schema、验收检查点（含失败去向）、失败计数、跨会话交接 |
| `experiment-driven-doc` | 自动触发 | 决策价值门 + 验收判据阶梯 + 实验记录模板 |
| `agent-heartbeat` | 自动触发 | 长命令心跳，防止用户误判卡死 |
| `remote-exec` | 显式调用 | SSH/认证、选节点、tmux detach、存储治理、远端失败自修表 |
| `code-review` | 显式调用 | 审 PR/diff 的四段输出与 vibe-coding 识别；标准从被审 repo 取，取不到才回落 [P0-P4](https://github.com/zhaochenyang20/sglang-diffusion-routing/issues/32) |
| `code-to-kernel-diagram` | 显式调用 | `nn.Module` forward → 逐 kernel 数据流图 |
| `upstream-contribute` | 显式调用 | PR vs Issue 判断 + body 模板 |
| `research-to-blog` | 显式调用 | 文献调研 → 对外博客 / 公众号 |

### Rules（`.cursor/rules/`）

| rule | 管什么 |
|-------|--------|
| `agent-loop` | **循环的调度器**：定位当前在哪一格 → 点名去读哪个 skill；失败按类别自修，用尽才问人 |
| `narrative-spine` | 一条能被复述的主线；不为解释而膨胀；直接陈述当前为真的内容（语态的唯一归属处） |
| `reply-conclusion-first` | 对话回复：第一句即结论、只答被问到的对象、说「做不到」前先查 |
| `experiment-budget-gate` | 什么先自修、什么才停下来问人（中止清单的唯一归属处）、预算、每轮报改变哪条命令 |
| `external-output-boundary` | 跨出仓库边界三道检查：AI 披露（取自 [Ghostty AI Policy](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md)）、GPU 型号脱敏、去私料 |
| `code-hygiene` | 注释跟邻码一致只写 WHY；commit message 跟仓库风格、陈述改完后的状态 |
| `skill-authoring` | 写 `SKILL.md` 时的体量与内容约束（按 glob 挂载） |

### 一个知识点只有一个归属处

本库反复出现的失手是同一条判据写在三处，改的时候只改得动一处。归属表见
[`.cursor/skills/README.md`](.cursor/skills/README.md)，加新章节前先去那里找归属，
找到就只留链接。

### code 链路：`.cursor/rules/` 管不到 PR review

写代码与 commit 由 `code-hygiene` 管，审本地 diff 由 `code-review` 管，两者都在会话内生效。
**但 PR 上真正跑的那次 review 由 Cursor 云端 Bugbot 执行，它只读被审 repo 的
`.cursor/BUGBOT.md` 与 dashboard 的 Team / Repository Rules，不读 `.cursor/rules/*.mdc`，
也不读 Skills。** 要让某条标准在 PR 阶段生效，只能写进那两处。分阶段的完整对照表见
[`.cursor/skills/README.md`](.cursor/skills/README.md)。

### 闭环：调度器是 rule，不是 skill

控制结构是 `Goal → Plan → Select → Design → Execute → Evaluate →（pass）Close /（fail）
Diagnose → Repair → 下一个 task → Ship`，关键约束是**「遇到非预期情况」不等于「问人」**。

调度这件事由 [`agent-loop`](.cursor/rules/agent-loop.mdc) 这条**常驻 rule** 承担，而不是某个
skill。原因是机制层面的：rule（`alwaysApply: true`）每轮都在上下文里，skill 只有 name 与
description 在上下文、正文要被语义匹配命中才加载。**一个需要先被匹配命中才能开始调度的
调度器，本身就会经常匹配不上。** 之前的编排 skill 明明是自动触发却仍需反复提醒，就是这个原因。

各格的分工：

```text
Goal ─► PLAN ─► SELECT ─► DESIGN ─► EXECUTE ─► EVALUATE ─┬─ pass ─► CLOSE ─┐
         │        │          │          │                │                │
         │        │          │          │                └─ fail ─► DIAGNOSE
  feature-dev  task-loop  experiment- remote-exec                     │
   -pipeline              driven-doc                          按类别自修，用尽才问人
         │                                                            │
         └──────────────── 下一个 task ◄──────────────────────────────┘
                                  │
                         全部通过 ─► SHIP: code-review → upstream-contribute
```

失败分流是闭环的关键，四类去向：环境/瞬时错误走 `remote-exec` 的失败处置表自修；契约不匹配走
`experiment-driven-doc` 的层 0 复现样例；**假设被推翻算结果不算故障**，回填后重排优先级继续；
判据失效就沿验收判据阶梯往任务指标退。四类都用尽重试上限，才查 `experiment-budget-gate`
的中止清单——到这一步才轮到停下问人。

`task.md` 是任务状态的唯一真相源，schema 与验收检查点的写法归 `task-loop`。

---

## 安装到 Cursor 全局目录

Cursor 只读取全局目录：Skills 在 `~/.cursor/skills-cursor/`，Rules 在 `~/.cursor/rules/`。
本库整个链接过去，改完文件立即生效，不需要重装。

链接方式对两者不同，原因是全局 `skills-cursor/` 里还混着 Cursor 自带的 skill，
不能整目录替换：

| 目标 | 方式 |
|---|---|
| `rules/` | **整目录 junction / 软链接**。`git pull` 替换目录内的文件不会断开它 |
| `skills-cursor/` | **逐个 skill 建 junction**。加删 skill 后要重跑安装脚本 |

> **不要用硬链接（`mklink /H`）链 rules。** 硬链接绑的是文件本身，`git pull` / `git checkout`
> 是「删掉重写」，一拉就断，之后仓库改动再也不会反映到 Cursor——而且没有任何报错。

### Windows（PowerShell，无需管理员）

```powershell
git clone https://github.com/ZJLi2013/my_skills.git   # 如未 clone
cd my_skills

# 1. Rules —— 整目录 junction
$rulesDest = "$env:USERPROFILE\.cursor\rules"
if (Test-Path $rulesDest) {
    if (-not (Get-Item $rulesDest).LinkType) {
        Move-Item $rulesDest "$rulesDest-backup-$(Get-Date -f yyyyMMdd)"   # 保住本地独有的 rule
    } else { Remove-Item $rulesDest -Force }
}
cmd /c "mklink /J `"$rulesDest`" `"$PWD\.cursor\rules`""

# 2. Skills —— 先清失效链接，再补新增的（幂等，可反复跑）
$skillsDest = "$env:USERPROFILE\.cursor\skills-cursor"
Get-ChildItem $skillsDest -Force | Where-Object { $_.LinkType -eq 'Junction' -and -not (Test-Path ($_.Target -join '')) } |
    ForEach-Object { cmd /c "rmdir `"$($_.FullName)`""; Write-Host "Pruned: $($_.Name)" }
Get-ChildItem "$PWD\.cursor\skills" -Directory | ForEach-Object {
    $t = Join-Path $skillsDest $_.Name
    if (-not (Test-Path $t)) { cmd /c "mklink /J `"$t`" `"$($_.FullName)`""; Write-Host "Linked: $($_.Name)" }
}

# 3. 私有配置
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor\configs" | Out-Null
cmd /c "mklink /H `"$env:USERPROFILE\.cursor\configs\node_inventory.yaml`" `"$PWD\.cursor\configs\node_inventory.yaml`""
```

### macOS / Linux（Terminal）

```bash
git clone https://github.com/ZJLi2013/my_skills.git   # 如未 clone
cd my_skills

# 1. Rules —— 整目录软链接
RULES_DEST="$HOME/.cursor/rules"
if [ -e "$RULES_DEST" ] && [ ! -L "$RULES_DEST" ]; then
    mv "$RULES_DEST" "$RULES_DEST-backup-$(date +%Y%m%d)"
fi
ln -sfn "$PWD/.cursor/rules" "$RULES_DEST"

# 2. Skills —— 先清失效链接，再补新增的
SKILLS_DEST="$HOME/.cursor/skills-cursor"
mkdir -p "$SKILLS_DEST"
find "$SKILLS_DEST" -maxdepth 1 -type l ! -exec test -e {} \; -print -delete
for d in "$PWD/.cursor/skills"/*/; do
    t="$SKILLS_DEST/$(basename "$d")"
    [ -e "$t" ] || { ln -s "$d" "$t"; echo "Linked: $(basename "$d")"; }
done

# 3. 私有配置
mkdir -p "$HOME/.cursor/configs"
ln -sf "$PWD/.cursor/configs/node_inventory.yaml" "$HOME/.cursor/configs/node_inventory.yaml"
```

### 验证安装结果

**要验的是链接类型，不是文件在不在**——漂移时文件都在，只是变成了各自独立的副本。

```powershell
# Windows：rules 必须是 Junction；skills 不能有 target-exists=False
(Get-Item "$env:USERPROFILE\.cursor\rules").LinkType
Get-ChildItem "$env:USERPROFILE\.cursor\skills-cursor" -Force |
    Where-Object { $_.LinkType -eq 'Junction' } |
    ForEach-Object { "{0,-30} {1}" -f $_.Name, (Test-Path ($_.Target -join '')) }
```

```bash
# macOS / Linux：rules 必须带 -> 指向 my_skills
ls -ld ~/.cursor/rules
find ~/.cursor/skills-cursor -maxdepth 1 -type l ! -exec test -e {} \; -print   # 应无输出
```

安装后 Cursor 重启即可，**所有项目无需额外配置**，Agent 自动获得这些 Skills 与 Rules。

---

## 其他项目中如何使用

安装到全局目录后，在任意 Cursor 项目里向 Agent 提问时，Skills 会自动出现在
`available_skills` 列表中。使用方式示例：

```
# 在 lerobot 项目中（点名冷 skill）
"用 remote-exec，ssh 到 david@ip 修 GitHub 认证"
→ Agent 读取该 skill 后执行

# 推进大 feature（自动 skill）
"按 backlog 做下一个 sub-task"
→ Agent 使用 feature-dev-pipeline
```

不需要在每个项目的 `.cursor/` 下放置 Skill 文件。

---

## 私有配置（GPU 节点凭证）

`.cursor/configs/` 目录已 git-ignore，不会入库。需手动在本地创建：

```bash
# 从模板创建（首次）
cp .cursor/configs/node_inventory.yaml.example .cursor/configs/node_inventory.yaml
# 编辑填入真实节点信息（字段含义见 remote-exec/reference.md）
```

`node_inventory.yaml` 是唯一的节点配置格式；`remote-exec` 在它缺失时退回
`gpu_nodes.list`（每行一个 SSH host）。安装脚本会把它硬链接到
`~/.cursor/configs/`，Agent 统一从该全局路径读取，无需在每个项目重复配置。

---

## 更新 Skills

直接在 `my_skills` 仓库修改 SKILL.md，保存后立即生效（Junction/软链接同步）：

```bash
git pull origin main   # 获取最新版
# Cursor Agent 下次调用时自动使用新版本，无需重新安装
```

---

## 参考资源

- [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) — Anthropic 官方：怎么写 skill、progressive disclosure、eval 循环、description 触发优化。本库在 Cursor 里写 skill 走内置 `create-skill`；体量约束在 [`.cursor/rules/skill-authoring.mdc`](.cursor/rules/skill-authoring.mdc)。
- [claude code skills (官方仓库)](https://github.com/anthropics/skills)
- [awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
- [cowork-skills](https://github.com/ZhangHanDong/cowork-skills)
- [AI-Infra-Auto-Driven-SKILLS](https://github.com/BBuf/AI-Infra-Auto-Driven-SKILLS)
