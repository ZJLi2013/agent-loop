# my_skills

个人 Agent Skills 库，面向 **Cursor** 的可复用工作流集合。部分高风险/长任务 Skills 默认不自动启用，需显式点名调用。

---

## 目录结构

```
my_skills/
├── .cursor/
│   ├── skills/                              # Cursor Agent Skills
│   │   ├── agent-heartbeat/                 # 长任务心跳防超时
│   │   ├── cross-agent-contract/            # 双 agent 经共享 md 对齐集成契约
│   │   ├── cursor-overnight-task-manager/   # 批量夜间 GPU 测试（显式调用）
│   │   ├── experiment-driven-doc/           # 实验驱动文档追踪
│   │   ├── gpu-cluster-resource-manager/    # 多节点 GPU 资源调度
│   │   ├── long-running-agent-harness/       # 长任务编排与跨会话交接
│   │   ├── local-push-remote-pull-test/      # 本地 push + 远端 pull/test
│   │   ├── remote-ssh-github-auto/          # 远端 SSH + GitHub 认证
│   │   ├── research-to-blog/                # 文献调研 → 自媒体/公众号成品
│   │   ├── tmux-remote-detach/              # 远端 tmux 托管长任务（显式调用）
│   │   └── upstream-contribute/             # 实验后评估上游贡献（显式调用）
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
| `agent-heartbeat` | 自动触发 | 长任务（训练/编译/推理）心跳输出，防止用户误判卡死 |
| `cross-agent-contract` | 显式调用 | 两个互相依赖的 agent/repo（消费方 A + 组件方 B）经单一共享 md 契约文档对齐：gaps 表 + 消费方驱动的 API 建议 + 钉死契约 + dated 双向握手 + 各 repo dated recheck 便条 |
| `cursor-overnight-task-manager` | 显式调用 | 批量夜间测试：读取 repo 列表 → SSH 到远端 AMD GPU → headless run → 报告 |
| `experiment-driven-doc` | 自动触发 | 实验驱动文档：假设 → 设计 → 执行 → 结果 → 分析 → next step 全流程追踪 |
| `gpu-cluster-resource-manager` | 条件触发 | 多节点 GPU 集群资源管理：探测 → 亲和性打分 → 节点选择 → 存储治理 |
| `long-running-agent-harness` | 自动触发 | 长任务总控：initializer → task loop → verification gates → durable handoff |
| `local-push-remote-pull-test` | 条件触发 | 本地 push → 远端 pull → 远端测试完整工作流 |
| `remote-ssh-github-auto` | 条件触发 | SSH Agent Forwarding + 远端 GitHub 认证修复 |
| `research-to-blog` | 条件触发 | 文献调研 → 事实核实 → 内部消化 → 谋篇去重 → 客观化去 AI 味 → 标题/配图/References → 内外分离，产出对外博客/公众号 |
| `tmux-remote-detach` | 显式调用 | 远端 tmux 托管长任务，支持断线恢复、日志持久化、批量状态检查 |
| `upstream-contribute` | 显式调用 | 实验完成后评估是否值得向上游提交 PR / Issue，并生成草稿 |

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
# 在 lerobot 项目中
"通过 ssh david@ip_address 登录远端GPU节点，执行训练脚本"
→ Agent 自动调用 remote-ssh-github-auto Skill

# 在任意 Python 项目中
"为这个 Python 项目生成 Dockerfile"
→ Agent 自动调用 dockerfile_generator Skill
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

- [claude code skills (官方)](https://github.com/anthropics/skills)
- [awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
- [cowork-skills](https://github.com/ZhangHanDong/cowork-skills)
- [AI-Infra-Auto-Driven-SKILLS](https://github.com/BBuf/AI-Infra-Auto-Driven-SKILLS)
