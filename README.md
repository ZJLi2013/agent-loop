# my_skills

个人 Agent Skills 库，面向 **Cursor** 的可复用工作流集合。部分高风险/长任务 Skills 默认不自动启用，需显式点名调用。

---

## 目录结构

```
my_skills/
├── .cursor/
│   ├── skills/                              # Cursor Agent Skills
│   │   ├── agent-heartbeat/                 # 长任务心跳（自动）
│   │   ├── experiment-driven-doc/           # 实验记录（自动）
│   │   ├── feature-dev-pipeline/            # feature backlog 编排（自动）
│   │   ├── long-running-agent-harness/       # 跨会话编排（自动）
│   │   ├── code-to-kernel-diagram/          # 模块源码 → kernel 数据流图
│   │   ├── cross-agent-contract/            # 双 agent 经共享 md 对齐契约
│   │   ├── cursor-overnight-task-manager/   # 批量夜间 GPU 测试
│   │   ├── gpu-cluster-resource-manager/    # 多节点 GPU 资源调度
│   │   ├── local-push-remote-pull-test/      # 本地 push + 远端 pull/test
│   │   ├── nv_physical_ai_tracker/          # NVIDIA Physical AI 追踪
│   │   ├── remote-ssh-github-auto/          # 远端 SSH + GitHub 认证
│   │   ├── research-to-blog/                # 文献调研 → 自媒体
│   │   ├── tmux-remote-detach/              # 远端 tmux 托管长任务
│   │   ├── upstream-contribute/             # 实验后评估上游贡献
│   │   └── video-frame-analysis/            # 视频抽帧目视调试
│   ├── agents/                              # Cursor Agent 定义
│   │   ├── replan.md                        # 实验 review & 优先级调整
│   │   └── code_run_plan.md                 # 代码执行 & 实验闭环
│   └── configs/                             # 本地私有配置（git-ignored）
│       ├── gpu_nodes.list                   # SSH 节点清单（用户自建）
│       └── gpu_nodes.list.example           # 节点清单模板
└── .gitignore
```

---

## Skills 列表

| skill | 启用方式 | 描述 |
|-------|----------|------|
| `feature-dev-pipeline` | 自动触发 | 大 feature → 子任务 → 设计 → 实现+实验 → 回填 |
| `experiment-driven-doc` | 自动触发 | 实验驱动文档：假设 → 设计 → 结果 → 结论 |
| `long-running-agent-harness` | 自动触发 | 长任务总控：initializer → loop → gates → handoff |
| `agent-heartbeat` | 自动触发 | 长命令心跳，防止用户误判卡死 |
| `code-to-kernel-diagram` | 显式调用 | `nn.Module` forward → 逐 kernel 数据流图 |
| `cross-agent-contract` | 显式调用 | 两 repo 经共享 md 对齐集成契约 |
| `cursor-overnight-task-manager` | 显式调用 | 批量夜间远端 GPU 测试 |
| `gpu-cluster-resource-manager` | 显式调用 | 探测节点、选机、管缓存与磁盘 |
| `local-push-remote-pull-test` | 显式调用 | 本地 push → 远端 pull → 远端测试 |
| `nv-physical-ai-tracker` | 显式调用 | NVIDIA Physical AI / 机器人研究进展追踪 |
| `remote-ssh-github-auto` | 显式调用 | SSH 登录 + 远端 GitHub 认证修复 |
| `research-to-blog` | 显式调用 | 文献调研 → 对外博客 / 公众号 |
| `tmux-remote-detach` | 显式调用 | 远端 tmux 托管长任务 |
| `upstream-contribute` | 显式调用 | 实验后评估是否提上游 PR / Issue |
| `video-frame-analysis` | 显式调用 | 从 mp4 抽帧目视，落成可追溯结论 |

### 长任务 Skill 边界

| 场景 | 首选 skill | 职责边界 |
|------|------------|----------|
| 长任务跨会话、需要 runbook / progress / handoff | `long-running-agent-harness` | 外层编排，不负责具体远端执行细节 |
| 假设验证、ablation、debug 实验记录 | `experiment-driven-doc` | 写实验设计、结果、分析和 next step |
| 批量夜间测试多个 repo | `cursor-overnight-task-manager` | 执行 overnight batch workflow |
| 单个长命令需要用户可见进度 | `agent-heartbeat` | 输出心跳和阶段进度 |
| 远端任务需要本地断开后继续跑 | `tmux-remote-detach` | 创建/恢复 tmux session 和日志 |

### Agents

| agent | 描述 |
|-------|------|
| `replan` | 实验文档 review、分析质量检查、优先级调整 |
| `code_run_plan` | 基于实验计划执行代码编写、远端运行、结果回填 |

---

## 安装到 Cursor 全局目录

Cursor Agent 只读取 `~/.cursor/skills-cursor/` 下的 Skills。
本库通过 **目录 Junction（Windows）/ 软链接（macOS/Linux）** 链接到该全局目录，
修改 SKILL.md 后无需重复安装，自动生效。

### Windows（PowerShell，无需管理员）

```powershell
# 1. clone 本库（如未 clone）
git clone https://github.com/ZJLi2013/my_skills.git
cd my_skills

# 2. 一键安装：将所有 Skills 链接到 Cursor 全局目录
$skillsSource = "$PWD\.cursor\skills"
$skillsDest   = "$env:USERPROFILE\.cursor\skills-cursor"

Get-ChildItem $skillsSource -Directory | ForEach-Object {
    $target = Join-Path $skillsDest $_.Name
    if (Test-Path $target) {
        Write-Host "Already exists (skip): $($_.Name)"
    } else {
        cmd /c "mklink /J `"$target`" `"$($_.FullName)`""
        Write-Host "Linked: $($_.Name)"
    }
}

# 3. 链接私有配置文件（硬链接，无需管理员）
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor\configs" | Out-Null
cmd /c "mklink /H `"$env:USERPROFILE\.cursor\configs\gpu_nodes.env`" `"$PWD\.cursor\configs\gpu_nodes.env`""
```

### macOS / Linux（Terminal）

```bash
# 1. clone 本库（如未 clone）
git clone https://github.com/ZJLi2013/my_skills.git
cd my_skills

# 2. 一键安装：将所有 Skills 软链接到 Cursor 全局目录
SKILLS_SRC="$PWD/.cursor/skills"
SKILLS_DEST="$HOME/.cursor/skills-cursor"
mkdir -p "$SKILLS_DEST"

for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name=$(basename "$skill_dir")
    target="$SKILLS_DEST/$skill_name"
    if [ -e "$target" ]; then
        echo "Already exists (skip): $skill_name"
    else
        ln -s "$skill_dir" "$target"
        echo "Linked: $skill_name"
    fi
done

# 3. 链接私有配置
mkdir -p "$HOME/.cursor/configs"
ln -sf "$PWD/.cursor/configs/gpu_nodes.env" "$HOME/.cursor/configs/gpu_nodes.env"
```

### 验证安装结果

```powershell
# Windows
dir "$env:USERPROFILE\.cursor\skills-cursor"
# 应看到 <JUNCTION> 条目指向 my_skills 对应目录

# macOS / Linux
ls -la ~/.cursor/skills-cursor/
```

安装后 Cursor 重启即可，**所有项目无需额外配置**，Agent 自动获得这些 Skills。

---

## 其他项目中如何使用

安装到全局目录后，在任意 Cursor 项目里向 Agent 提问时，Skills 会自动出现在
`available_skills` 列表中。使用方式示例：

```
# 在 lerobot 项目中（点名冷 skill）
"用 remote-ssh-github-auto，ssh 到 david@ip 修 GitHub 认证"
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
# gpu_nodes.env —— 节点连接信息（含密码，不入库）
NODE_4090_HOST=<ip>
NODE_4090_USER=<username>
NODE_4090_AUTH=<password>          # password 认证节点填此项
NODE_4090_KEY=~/.ssh/id_ed25519    # key 认证节点填此项
NODE_4090_REPO=/home/<user>/robot
```

安装脚本会将此文件硬链接到 `~/.cursor/configs/gpu_nodes.env`，
Agent 通过 Skills 统一从该全局路径读取，无需在每个项目重复配置。

```bash
# 从模板创建（首次）
cp .cursor/configs/gpu_nodes.list.example .cursor/configs/gpu_nodes.list
# 编辑填入真实节点信息
```

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
