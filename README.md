# my_skills

个人 Agent Skills 库，面向 **Cursor** 的可复用工作流集合。部分高风险/长任务 Skills 默认不自动启用，需显式点名调用。

---

## 目录结构

```
my_skills/
├── .cursor/
│   ├── skills/                          # Cursor Agent Skills
│   │   ├── feature-planning/            # 大 feature 拆子任务（自动）
│   │   ├── task-state/                   # task.md、验收检查点、交接（自动）
│   │   ├── experiment-design/           # 实验两道门 + 记录模板（自动）
│   │   ├── agent-memory/                # 跨会话保住的具体值（自动）
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
| `feature-planning` | 自动触发 | 大 feature → 子任务 → 设计 → 实现+实验 → 回填 |
| `task-state` | 自动触发 | `task.md` schema、验收检查点（含失败去向）、失败计数、跨会话交接 |
| `experiment-design` | 自动触发 | 决策价值门 + 验收判据阶梯 + 实验记录模板 |
| `agent-memory` | 自动触发 | `.cursor/memory/facts.md`：跨会话要保住的具体值，就地覆盖、开工前验证 |
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
| `write-for-humans` | **一切给人看的产出**（回复与文档共用）：结论先行、一条主线、不为解释而膨胀、只答被问到的对象、直接陈述真值、说「做不到」前先查 |
| `when-to-stop` | 什么先自修、什么才停下来问人（**中止清单的唯一归属处**）、预算、每轮报改变哪条命令 |
| `external-output-boundary` | 跨出仓库边界三道检查：AI 披露（取自 [Ghostty AI Policy](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md)）、GPU 型号脱敏、去私料 |
| `code-hygiene` | 注释跟邻码一致只写 WHY；commit message 跟仓库风格、陈述改完后的状态 |
| `shell-exec` | 多行命令先写文件再执行；PowerShell 三个会静默失败的坑 |
| `kiss` | 先想最简解法；方案超过 3 步就停下重想 |
| `authoring` | 写 `SKILL.md` 或 `.mdc` 时的准入、体量、归属；**一条约束该放 rule / skill / hook 的判据**（按 glob 挂载） |

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
Diagnose → Repair → 下一个 task → Done`，关键约束是**「遇到非预期情况」不等于「问人」**。

调度这件事由 [`agent-loop`](.cursor/rules/agent-loop.mdc) 这条**常驻 rule** 承担，而不是某个
skill。原因是机制层面的：rule（`alwaysApply: true`）每轮都在上下文里，skill 只有 name 与
description 在上下文、正文要被语义匹配命中才加载。**一个需要先被匹配命中才能开始调度的
调度器，本身就会经常匹配不上。** 之前的编排 skill 明明是自动触发却仍需反复提醒，就是这个原因。

各格的分工：

```text
Goal ─► PLAN ─► SELECT ─► DESIGN ─► EXECUTE ─► EVALUATE ─┬─ pass ─► CLOSE ─┐
         │        │          │          │                │                │
         │        │          │          │                └─ fail ─► DIAGNOSE
  feature-     task-state  experiment-  │                            │
   planning                design       │              按类别自修，用尽才问人
         │                              │                            │
         └──────────────── 下一个 task ◄─┴────────────────────────────┘
                                  │
                         全部通过 ─► DONE（报告并停）

         .cursor/memory/facts.md  ← 要用一个具体值就读它，第二次用到就写回
              （横穿每一格，不是其中一格）
```

**`agent-memory` 不是环上的格子。** 关键规则是「**文件是真相源，对话是缓存**」——要把一个值
放进命令时读文件，而不是凭印象。这样就不需要察觉自己有没有被压缩：开了一天没关的窗口里根本
没有「开工」这个时刻可以挂重读，而上下文被裁掉时事实是静默消失的。`agent-heartbeat` 同样横穿
整个环，它挂在任何预计超过 60 秒的命令上。

循环内每一格的触发条件都是机械可判的。`remote-exec`、`code-review`、`upstream-contribute`、
`research-to-blog`、`code-to-kernel-diagram` **都在循环之外**，只有你明确要了才走——
`task.md` 清空意味着 DONE，不意味着该去开 PR。

失败分流是闭环的关键，四类去向：环境/瞬时错误自己修，同类最多两次并计入失败计数（跑远端 GPU
时具体修法见 `remote-exec` 的失败处置表）；契约不匹配走 `experiment-design` 的层 0 复现样例；
**假设被推翻算结果不算故障**，回填后重排优先级继续；判据失效就沿验收判据阶梯往任务指标退。
四类都用尽重试上限，才查 `when-to-stop` 的中止清单——到这一步才轮到停下问人。

`task.md` 是任务状态的唯一真相源，schema 与验收检查点的写法归 `task-state`。

### memory：工作项目的 `.cursor/memory/` + 一个强制注入的 hook

**记忆属于被开发的那个项目，本库只发模板与 hook。** 在工作项目下建四个文件：
`INDEX.md`（目录，常驻）/ `facts.md`（覆盖）/ `episodes.md`（跑过什么、被推翻了什么、
排除了什么）/ `lessons.md`（上限 15 条，`[x3]` 晋升为规则）。procedural memory 就是
`.cursor/skills/` 本身，不另建索引。模板在
[`agent-memory/templates/`](.cursor/skills/agent-memory/templates/)。

**检索不由 agent 决定。** `postToolUse` 是 Cursor 唯一能返回 `additional_context` 的 hook 事件，
挂上 `Read` matcher 之后，**读 `task.md` 会无条件注入索引 + 词面命中的 0~5 条**。
写成规则的版本仍然是「让 LLM 判断自己不知道什么」，而那正是不可靠的地方。
无命中时会明说库存条数——索引坏了和确实没做过必须可区分。

写入挂在**转换**上（task 关闭 / 假设被推翻 / 方案被否决 / 被挡住 / 自修成功 / 值变了 / pivot），
不挂在「我发现了一个事实」上——后者是判断题，要先意识到才触发。

### 具体的值：`facts.md`

跑久了 agent 会忘掉用的是哪个远端节点、哪个容器、哪个 checkpoint 路径。**交接笔记救不了
这个**——它按时间追加，第 1 天写下的节点名到第 3 天已经被十条记录埋掉。

解法是一份**就地覆盖、只留当前值**的 `facts.md`。准入判据两条同时成立：后面每轮都要用，
且重查一次要花条命令。写入时机挂在「一个值第二次被用到」这个动作上，不依赖想起来。
新 session 开工先读它并验证要用到的那几条——**过期的事实比缺失的更坏，它不会报错**，
命令照常执行，只是打在了错的机器上。

三份跨会话产物的区别在**追加还是覆盖**：`facts.md` 覆盖（当前值），`task.md` 改状态列，
`.cursor/progress.md` 追加（这一轮发生了什么）。具体的值只写进第三份，三天后就被埋掉了。

这和 [Anthropic 给 long-horizon agent 的方案](https://www.anthropic.com/news/context-management)
是同一个形状：memory tool 展开就是一个 `/memories` 目录加几个文件操作，没有向量库。
本库同样不做检索——每个任务的常量大约十行，精确查找就够，
把 key-value 塞进语义检索反而会取回相邻的那一条。

判据与扩展方式见 [`agent-memory`](.cursor/skills/agent-memory/SKILL.md)。

### 还缺：VERIFY（TODO）

**没人问「这个通过是真的吗」。** 现在 EVALUATE 只判断检查点过没过。测试通过可能是因为它被
skip 了，指标变好可能是因为 baseline 自己坏了，断言可能压根没执行到。假通过的代价比普通失败
高——task 被标 `✅`，循环继续往前走，错误在几个 task 之后才浮出来。可能的补法：在 pass 分支
加一道 VERIFY，要求用检查点的**实际输出**而不是退出码来判定。

**防漂移靠不变量,不靠提醒。** `task.md` 里有且只有一行 `🔬 doing`,一次改动属于它的唯一判据是
「会让那行的验收检查点从不通过变成通过吗」;不属于就先建新行再动手,`🚧 blocked` 的个数就是
嵌套深度,超过两层停下问人。写成「自查有没有漂」的规则永远不会触发——漂移的每一步看着都合理,
那个自省时刻不会到来,所以判据必须落在一个已经写下来的检查点上。

---

## 同步到 Cursor 全局目录

Cursor 只读全局目录：Skills 在 `~/.cursor/skills-cursor/`，Rules 在 `~/.cursor/rules/`。
本库链接过去之后，改文件立即生效。

```powershell
git clone https://github.com/ZJLi2013/my_skills.git   # 如未 clone
cd my_skills
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

**每次增删或重命名 skill 之后重跑一次**——脚本幂等，会清掉失效的 junction、补上新增的，
最后打印一遍链接类型供核对。跑完重启 Cursor，所有项目自动获得这些 Skills 与 Rules。

### 为什么是 junction 而不是硬链接

| 目标 | 方式 | 原因 |
|---|---|---|
| `rules/` | 整目录 junction | 整个目录都归本库，可以替换 |
| `skills-cursor/` | 逐个 skill 建 junction | 该目录里混着 Cursor 自带的 skill，不能整目录替换 |

> **不要用硬链接（`mklink /H`）链 rules。** 硬链接绑的是文件本身，而 `git pull` /
> `git checkout` 是「删掉重写」，一拉就断——之后仓库改动再也不会反映到 Cursor，
> **而且不会有任何报错**：文件都还在，只是变成了各自独立的副本。

macOS / Linux 把 junction 换成 `ln -s` 即可，逻辑相同；本库目前只在 Windows 上用，没有备 .sh。

---

## 其他项目中如何使用

安装到全局目录后，在任意 Cursor 项目里向 Agent 提问时，Skills 会自动出现在
`available_skills` 列表中。使用方式示例：

```
# 在 lerobot 项目中（点名冷 skill）
"用 remote-exec，ssh 到 david@ip 修 GitHub 认证"
→ Agent 读取该 skill 后执行

# 推进大 feature（自动 skill）
"按 task.md 做下一个 sub-task"
→ Agent 使用 feature-planning
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

- [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) — Anthropic 官方：怎么写 skill、progressive disclosure、eval 循环、description 触发优化。本库在 Cursor 里写 skill 走内置 `create-skill`；体量约束在 [`.cursor/rules/authoring.mdc`](.cursor/rules/authoring.mdc)。
- [claude code skills (官方仓库)](https://github.com/anthropics/skills)
- [awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)
- [cowork-skills](https://github.com/ZhangHanDong/cowork-skills)
- [AI-Infra-Auto-Driven-SKILLS](https://github.com/BBuf/AI-Infra-Auto-Driven-SKILLS)
