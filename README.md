# agent-loop

面向 **Cursor** 的 agent 控制环：**每一步判断该继续、该换一条、还是该停，并且默认继续。**

主体是 7 条常驻 rule 与 1 个 hook 组成的控制层——它决定失败之后自修还是上报、跑偏时怎么拉回、
无人值守时把「被挡住」从「等人」改成「跳过做下一条」。skills 是这个环路由过去的 playbook，
不是产品本身。

```text
agent-loop/
├── rules/           # 常驻约束，每轮都在上下文（控制层主体）
└── .cursor/
    ├── skills/      # 按需加载的 playbook，清单与归属见 skills/README.md
    ├── hooks/       # 模型之外的执行者，目前只有 memory 注入
    └── memory/      # 本库自己的记忆；工作项目各有一份
```

---

## 三层分工

判据是**agent 能不能无视它**。能无视的是 prompt，不能无视的才是 harness。

| 层 | 职责 | 在本库是什么 | 现状 |
|---|---|---|---|
| Agent | think / plan / execute / diagnose / replan | 8 条 rule（7 条常驻）+ 10 个 skill，约 1600 行 markdown | ✅ |
| **Harness** | run / timeout / retry / rollback / checkpoint / persist state / capture logs | `hooks/memory-lookup.py`（122 行）+ `task.md`、`.cursor/memory/` 两份状态 | ⚠️ 最大缺口 |
| **Verifier** | 这件事真的做完了吗：指标动了吗、测试过了吗、证据够吗 | — | ❌ 空缺 |

---

## 安装

```powershell
git clone https://github.com/ZJLi2013/agent-loop.git
cd agent-loop
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

脚本幂等，把 `rules/`、每个 skill、`hooks/` 链接到 `~/.cursor/` 并合并 `hooks.json`，
最后打印链接类型供核对。**跑完重启 Cursor**，之后所有项目自动获得这些 rule 与 skill，
不需要在每个项目的 `.cursor/` 下放文件。

增删或重命名 skill 之后、**以及本仓库改名或移动之后**，重跑一次。

**rules 与 hook 清单只存在于 user 级一份。** 源目录是仓库根的 `rules/`，不是 `.cursor/rules/`：
`~/.cursor/rules` 是指向它的 junction，而 Cursor 会把项目级与 user 级**两层都加载**——
两处都有就是每条 rule 进上下文两遍。同理本仓库不放 `.cursor/hooks.json`（memory 会被注入两份）。

> **不要用硬链接（`mklink /H`）。** 硬链接绑的是文件本身，而 `git pull` / `git checkout`
> 是「删掉重写」，一拉就断——之后仓库改动再也不会反映到 Cursor，**且不会有任何报错**。
> 同类陷阱：仓库改名后 junction 指向不存在的路径，`Test-Path` 对目录仍返回 True，
> hook 照常执行、退出码 0，只是永远没有输出。

macOS / Linux 把 junction 换成 `ln -s`，逻辑相同；本库目前只在 Windows 上用。

`remote-exec` 需要的节点凭证放 `.cursor/configs/node_inventory.yaml`（该目录已 git-ignore，
需手动创建，字段含义见 `remote-exec/reference.md`）。缺失时退回 `gpu_nodes.list`，每行一个 SSH host。

---

## 使用

在新 repo 里只需要拷一次 memory 模板：

```powershell
mkdir .cursor\memory
copy $env:USERPROFILE\.cursor\skills-cursor\agent-memory\templates\*.md .cursor\memory\
```

然后直接说「我要做 X」，agent 会自己建 `task.md` 并开始跑。rules、skills、hooks 已全局生效，
`.cursor/memory/` 是唯一属于每个项目自己、装不过来的东西。

---

## Rules（`rules/`）

前 7 条 `alwaysApply: true`，每轮都在上下文；`authoring` 按 glob 挂在 `SKILL.md` 与 `.mdc` 上。

| rule | 管什么 |
|---|---|
| `agent-loop` | **循环的调度器**：定位当前在哪一格 → 点名去读哪个 skill；失败按类别自修，用尽才问人 |
| `when-to-stop` | 什么先自修、什么才停下来问人（**中止清单的唯一归属处**）、预算、每轮报改变哪条命令 |
| `write-for-humans` | 一切给人看的产出：结论先行、一条主线、不为解释而膨胀、直接陈述真值、说「做不到」前先查 |
| `external-output-boundary` | 跨出仓库边界三道检查：AI 披露（取自 [Ghostty AI Policy](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md)）、GPU 型号脱敏、去私料 |
| `code-hygiene` | 注释跟邻码一致、只写 WHY；commit message 跟仓库风格、陈述改完后的状态 |
| `shell-exec` | 多行命令先写文件再执行；PowerShell 三个会静默失败的坑 |
| `kiss` | 先想最简解法；方案超过 3 步就停下重想 |
| `authoring` | 写 `SKILL.md` / `.mdc` 的准入与体量；**一条约束该放 rule / skill / hook 的判据** |

---

## memory

**记忆属于被开发的那个项目，本库只发模板与 hook。** 设计理由、失败模式、以及换到个人助理场景哪些前提会失效，见 [`study/memory.md`](study/memory.md)。

---

## 跑在哪：Cursor vs 自建 LLM gateway

三层的可移植性完全不同：

| | 内容可移植 | 接线可移植 | 说明 |
|---|---|---|---|
| memory 文件 | ✅ | ✅ | 纯文本，零依赖 |
| rules / skills | ✅ | ❌ | 文本与平台无关，但**加载机制**是 Cursor 专有的 |
| hooks | ✅ | ❌ | 事件名、stdin/stdout 协议、`additional_context` 全是 Cursor 的 |

rules 靠 `.mdc` 的 `alwaysApply` frontmatter 常驻，skills 靠 name/description 做语义匹配注入。
「调度器必须是常驻 rule」这个结论本身就是 Cursor 加载机制的产物，换平台要重新判断。
Claude Code 有形状相似但字段不同的 hook 系统，`memory-lookup.py` 的逻辑可整段复用，接线要重写。

| | Cursor（当前） | 自建 LLM gateway |
|---|---|---|
| 免费拿到 | tool 执行与权限、diff 应用与 UI、上下文压缩、API 重试、subagent、Bugbot | 无，全要自己写 |
| 强制执行点 | 只能用 Cursor 开放的 hook 事件 | loop 是自己的代码，任意位置可插 |
| retry / 预算 / timeout | 模型自己数，harness 拦不住 | 几十行代码，天然强制 |
| rollback / checkpoint | 只有用户侧的会话 checkpoint，agent 无法在失败时程序化回滚 | 可做 |
| Verifier | 无处挂载 | 就是 EVALUATE 之后的一个函数 |
| 模型选择 | Cursor 支持的 | 任意，可按格子换模型 |

---

## 缺口

**VERIFY 没有。** EVALUATE 只判断检查点过没过，没人问「这个通过是真的吗」。测试通过可能是
因为它被 skip 了，指标变好可能是因为 baseline 自己坏了，断言可能压根没执行到。
假通过的代价比普通失败高——task 被标 `✅`，循环继续往前走，错误在几个 task 之后才浮出来。
落成机制的做法是把验收检查点写成**可执行命令**，由 hook 读它的实际输出与退出码，
而不是听 agent 声称它通过了。

**OBSERVE 没有独立节点。** 实验类由 `experiment-design` 覆盖，重构 / 修 bug 类的产物无人要求落盘。

**`stop` 原语未落地。** `agent 想退出 → harness 判断 completion criteria → 没完成 → 重新喂回去`
这个 Ralph primitive，在 Cursor 里的落点是 `stop` 事件，能把「继续」从模型自己选择变成
没有机会不继续。*未核实*：文档把 `stop` 描述为 "handle agent completion"，`loop_limit` 说明写着
"mainly for `stop` and `subagentStop` follow-up loops"，但输出字段表只给了 `subagentStop`
返回 `followup_message`。探针 `.cursor/hooks/stop-probe.py` 已装，只写日志、返回 `{}`。

**不做 task / hypothesis graph。** `task.md` 是扁平列表 + `blocked-by` 链，链长 ≥ 2 就停下问人。
这个上限是刻意的——改成图会让嵌套变廉价，恰好鼓励了要防的那件事。

---

## 参考

- [ralph](https://github.com/chrismdp/ralph) —— completion criteria 驱动的重投喂原语
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) —— failure 是 input，不是 termination condition
- [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) —— 怎么写 skill、progressive disclosure、description 触发优化
- [claude code skills](https://github.com/anthropics/skills) / [awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) / [cowork-skills](https://github.com/ZhangHanDong/cowork-skills) / [AI-Infra-Auto-Driven-SKILLS](https://github.com/BBuf/AI-Infra-Auto-Driven-SKILLS)
