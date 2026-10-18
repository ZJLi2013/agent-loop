# 在工作项目中使用 agent-loop

[Quickstart](quickstart.md) · [中文入口](../README.md) · [English entry](../en.md)

## 安装并选择模式

在 agent-loop 仓库里用 `python -m pip install .` 安装 CLI。Cursor enforced 模式改用 `python -m pip install -e .`：
安装器把 hooks 链接到仓库，可编辑安装能让 CLI 在切分支或 pull 之后仍与 hooks 用同一份代码。工作项目与
agent-loop 仓库分开放。

| 模式 | 得到什么 |
|---|---|
| Portable | CLI 命令与策略由宿主调用，生命周期由宿主自己管 |
| Cursor enforced | 下面的 Windows 安装器加上 memory、stop、preCompact hooks |
| dsh enforced | DeepSeek Harness 经 `hooks-codex` 桥接加上 stop 与 session-start hooks |

宿主与模型相互独立：模式决定宿主，宿主自己的 provider 配置决定模型。dsh worker 可以跑 DeepSeek、GPT 或任何
OpenAI / Anthropic 兼容的模型，agent-loop 这边不用改任何东西。

Windows + Cursor 下，在 agent-loop 仓库里运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

安装器把仓库链接进 `%USERPROFILE%\.cursor`，包括 rules 目录、各个 skill、harness 与 hooks。同名的普通目录会被移到
带时间戳的备份；有自定义 rules / hooks 时检查这些备份。装完重启 Cursor，并确认 Cursor 看得到的 Python 是 3.11+：
在终端里激活 venv 不一定改变 Cursor 的环境。仓库保持原位，并使用可信版本，见 [Security](../SECURITY.md)。

Windows 自动化任务在隔离 profile 里检查安装器接线，不启动 Cursor，也不保证兼容每个 Cursor 版本。发布前还要跑
[Releasing](releasing.md) 里的真实宿主冒烟。

<a id="dsh-enforced-mode"></a>
### dsh enforced 模式

dsh 需要 Node.js 24.2+；DeepSeek Harness Desktop 自带 dsh、Node 与 pnpm。命令行默认的 profile 是 `headless`，
`dsh web` 是 `web`，Desktop 是 `desktop`。

先把 rules 与 skills 分发到 dsh 的 home（`DSH_HOME`，dsh 默认是 `~/.dsh`），在 agent-loop 仓库里运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-to-dsh.ps1 -DshHome $HOME\.dsh
```

dsh 不读 `.mdc`，脚本把 always-apply 的 rules 去掉 frontmatter 后拼成 `$DSH_HOME/AGENTS.md`，所有 profile 的会话
都会加载它；这是生成文件，rules 改动后重跑。skills 逐个链接到 `$DSH_HOME/skills/`，那里的其他 skill 不动。
已有的手写 `AGENTS.md` 或同名普通 skill 目录会先移到带时间戳的备份。

hooks 还没有安装器，需手动把桥接接到 dsh profile `<p>` 上。

`dsh plugin` 依赖 pnpm，所以 pnpm 要在 `PATH` 上。`dsh-hook-protocol` 是桥接的 peer 依赖，不会自动安装。两个包都用
你所运行的 dsh 的版本号：

```powershell
dsh plugin --profile <p> add @deepseek-ai/dsh-hooks-codex@<dsh-version> @deepseek-ai/dsh-hook-protocol@<dsh-version>
```

在项目之外写一份 `hooks.json`。路径用绝对路径，因为 hooks 在会话的工作目录里运行（Windows 上经 pwsh）：

```json
{"hooks": {
  "SessionStart": [{"hooks": [{"type": "command", "command": "python <checkout>/adapters/dsh/hooks/memory-lookup.py", "timeout": 30}]}],
  "Stop": [{"hooks": [{"type": "command", "command": "python <checkout>/adapters/dsh/hooks/harness-stop.py", "timeout": 30}]}]
}}
```

在 `$DSH_HOME/profiles/<p>/cordis.patch.yml` 里挂载桥接（`DSH_HOME` 默认是 `~/.dsh`）：

```yaml
- insert:
    - id: hooks-codex
      name: '@deepseek-ai/dsh-hooks-codex'
      config:
        configPath: <absolute-path>/hooks.json
```

Desktop 的插件只能在退出 Desktop 时增删。欢迎页上的 Sign in 和 Add API Key 都只针对 DeepSeek 官方服务；
使用自己的 provider 时，点 Add API Key，输入框留空，再点 Set up later。

<a id="dsh-limitations"></a>
#### 已知限制

dsh 适配器是新加的，实际项目里跑得还少，下面的清单会随使用补充。

- **只管会话工作目录所在的项目。** 在项目根目录启动 dsh；Cursor 会绑定会话里读过 `task.md` 的每个项目，dsh 不会。
- **hooks 只挂在配置过的 profile 上。** 没挂 `hooks-codex` 的 profile（例如只给 reviewer 用的 `headless`）不受
  completion gate 约束。
- **没有压缩事件。** Goal Review 只靠动作数、时间与失败触发。
- **memory 索引只在会话开始时注入一次。** 桥接不传工具调用的文件路径，读 `task.md` 时不会再注入。
- **`AGENTS.md` 是生成的副本。** rules 改动后要重跑 `sync-to-dsh.ps1`；skills 是链接，跟着仓库变。
- **hooks 依赖仓库原位。** `hooks.json` 用的是仓库的绝对路径，仓库移动或切到不含 `adapters/dsh/` 的分支后 hooks 失败。
- **只在 Windows 上验证过。** 安装脚本是 PowerShell；其他平台的 rules / skills 需手动放到 `$DSH_HOME`。
- **Desktop GUI 里的 gate 未做端到端验证。** 端到端验证在 dsh headless 上完成；Desktop 用的是同一个桥接与配置方式。

<a id="dsh-models"></a>
### 在 dsh 里配置自己的模型

**worker 用哪个模型，完全由 dsh 的默认模型决定；agent-loop 只认宿主，不认模型。** 按 provider 类型选一条路：

| 你的模型来自 | 怎么配 |
|---|---|
| DeepSeek 官方 API | Desktop 欢迎页的 Add API Key，或模型页 DeepSeek 卡片里填 key |
| dsh 内置的第三方 provider（`openai`、`anthropic`、Kimi 的 `moonshotai`、GLM 的 `zai` 等） | 模型页 → 添加模型提供商 → 第三方模型提供商，选 provider 后填 key |
| 中转站、公司网关、自建 vLLM / SGLang 等 OpenAI 或 Anthropic 兼容端点 | 模型页 → 添加模型提供商 → 自定义模型 API；或直接写 `cordis.patch.yml` |

模型页在 Desktop 和 `dsh web` 的设置里。自定义模型 API 要填 Provider ID（之后不能改）、基础 URL、协议和 key，
「获取可用模型」会向端点的 `GET /models` 查询模型列表。key 存进 `$DSH_HOME/.credentials.yaml`，配置文件里只留引用。

不用 GUI 时，同样的内容写进 `cordis.patch.yml`。写在 `$DSH_HOME/cordis.patch.yml` 对所有 profile 生效，
写在 `$DSH_HOME/profiles/<p>/cordis.patch.yml` 只对该 profile 生效：

```yaml
- id: llm-pi-ai
  config:
    providers:
      my-endpoint:
        api: openai-completions          # 或 openai-responses / anthropic-messages
        baseURL: https://<endpoint>/v1
        apiKeyEnv: MY_ENDPOINT_KEY        # 先查 dsh 凭据库，再查同名环境变量
        models:
          - id: <model-id>
- id: agent-default-model
  config: { provider: my-endpoint, model: <model-id> }
```

几条容易踩的坑：

- **协议必须是端点实际提供的那一种。** 一个端点同时提供两种协议时，建两个 provider。部分 GPT 模型只有在
  `openai-responses` 上才同时接受工具调用与推理等级。
- **OpenAI 兼容端点后面的 DeepSeek V4 系列默认会思考。** 要让推理等级的 `off` 生效，给模型加上
  `compat: { thinkingFormat: deepseek }` 和 `reasoningEfforts: { off: , high: high }`。
- **key 和地址都对，端点却拒绝每个请求：** 在 provider 上加 `compat: { supportsDeveloperRole: false, maxTokensField: max_tokens }`。
- **端点要求自定义请求头**（例如网关自己的订阅头）：模型页编辑不了请求头，在 provider 上写 `headers: { <Header>: '<value>' }`。
  这样值会明文落在文件里，这个文件就不能进任何仓库。
- **Desktop 只继承用户级与系统级环境变量**，`apiKeyEnv` 引用的变量要设在那一级，或者直接在模型页填 key。

改完下一次请求即生效，不用重启。完整字段见 dsh 的
[配置模型指南](https://github.com/deepseek-ai/deepseek-harness/blob/main/docs/user/guide/providers.zh.md)。
reviewer 换另一个模型时，见下文「可选的独立 reviewer」里的 overlay 写法。

## 创建并评审计划

在工作项目里写一份 plan document，说明 Goal、范围、当前结论、下一个决策与验收判据，文件名不限。包含：

```text
Plan Revision: 1
Plan Review: proposed
```

创建 `.agent-loop/task.md`，把当前提议的 task 绑定到 `r1`。[示例 task](../examples/minimal-project/task.md) 展示了表格格式，
但它为了预批准演示从 `doing` 开始；新项目的 task 应从 `📝 proposed` 开始。

评审计划，然后把它设为 `Plan Review: approved`，并把一个 task 激活为 `🔬 doing`。配置了 reviewer 时，先按下文取得它的
plan review 建议。

在工作项目根目录，初始化一个适合该项目 Goal 的 verifier：

```sh
agent-loop-harness init --task t1 --plan-doc plan.md -- python -B -m unittest -v
```

把命令换成项目真实的测试或实验检查。初始化会锁定 verifier 命令与预算。工作经 `agent-loop-harness exec -- <command>` 执行，
然后运行 `agent-loop-harness verify`。宿主的其他工具调用不在 runner 的硬控制边界之内。默认在 runner 执行 3 个动作、
60 分钟或失败后触发 Goal Review，相关宿主事件也会触发刷新。`init --help` 列出预算与注意力相关的设置。

## 可选的独立 reviewer

在 plan review 和 task 初始化**之前**创建 `.agent-loop/reviewer.json`。它声明一条带超时的可执行命令，读取生成的
`.harness/review/prompt.md` 并遵守其中的输出约定。用你环境里可用的 reviewer CLI / 模型。概念上的配置是：

```json
{
  "argv": ["YOUR_REVIEWER_CLI", "YOUR_NONINTERACTIVE_ARGUMENTS"],
  "timeout_seconds": 1800
}
```

两个占位符都要换成真实的 argv 数组，上面这条不能直接运行。命令必须非交互运行、读取生成的 prompt，并写出它要求的
报告 / 决策。Windows worker 使用 WSL 里已有 reviewer CLI 的配置示例：

```json
{
  "argv": ["wsl.exe", "--", "bash", "-lc",
    "codex exec -s workspace-write 'Read .harness/review/prompt.md and follow it exactly.'"],
  "timeout_seconds": 1800
}
```

dsh 也可以做 reviewer 宿主，并用与 worker 不同的模型。headless 应用在参数为 `-` 时从 stdin 读任务；reviewer 模型放在
单独的 overlay 里，worker 的 profile 不用动：

```json
{
  "argv": ["cmd", "/c", "dsh --profile headless --patch <absolute-path>/reviewer.patch.yml - < .harness\\review\\prompt.md"],
  "timeout_seconds": 1800
}
```

overlay 只需覆盖默认模型；provider 已在 `cordis.patch.yml` 里声明时，只写最后一段即可：

```yaml
- id: llm-pi-ai
  config:
    providers:
      my-endpoint-responses:
        api: openai-responses
        baseURL: https://<endpoint>/v1
        apiKeyEnv: MY_ENDPOINT_KEY
        models:
          - id: <reviewer-model>
            reasoningEfforts: { high: high }
- id: agent-default-model
  config: { provider: my-endpoint-responses, model: <reviewer-model>, reasoningEffort: high }
```

这些示例要求 CLI 已安装并完成认证（Codex 示例要求在 WSL 中且能访问项目）。按你安装的工具 / 版本支持的命令写，
harness 不捆绑这些工具。凭据与模型选择由该工具负责。reviewer 配置是本地运行时配置，不应提交。生成的约定与角色边界见
[design.md](../design.md)。配置评审时，从 active task 链接项目的设计 / 计划，路径相对 `.agent-loop/task.md`（示例 task
已经这样做了）。

```sh
agent-loop-harness plan-review --plan-doc plan.md
```

读报告，批准或修改计划，激活 task，再按上文初始化。plan reviewer 只给建议，不能批准计划。某个 revision 的每个 open task
都已通过更早的 plan review 时，human 可以不再评审直接批准：`agent-loop-harness plan-review --plan-doc plan.md
--waive --reason "<human 的原话>"`，然后标记为 `approved`。连续 3 次 revise 结论，或连续 3 个 revision 没有实验时，
`plan-review` 拒绝再次运行 reviewer，直到 human 选择：用 `--continue --reason "<human 的原话>"` 再评审一次、带注记批准
（`--waive`）、原样批准上一个已评审的 revision，或停止。task 验证通过后，配置的 reviewer 自动运行，解读证据并选择
`continue`、`ask_human` 或 `stop`。提议的后继 task 需要按适用的批准策略显式激活。项目可以加
`.agent-loop/review-checklist.md` 写领域检查项；样例输入与实际输出能帮助 reviewer 判断这项工作是否度量了 Goal。

## 纠偏与 Goal Review

工作进行中要改 Goal 或范围时：

```sh
agent-loop-harness pause --require-revision --reason "Goal changed"
```

把计划更新为新 revision 并设为 proposed，同步 task 的 revision 与范围，配置了 reviewer 时取得 plan review，批准后运行
`agent-loop-harness resume`。

有待处理的 Goal Review 时，记录证据与决定：

```sh
agent-loop-harness goal-review --decision continue --evidence "The failed test identifies a repair within the approved Goal."
```

证据支持时用 `replan` 或 `stop`。`continue` 不会绕过必需的计划修订。

## Memory 与长任务观察

把 agent-loop 仓库 `skills/agent-memory/templates/` 下的四个 Markdown 模板复制到
`<working-project>/.agent-loop/memory/`。每个项目拥有自己的 facts、episodes、lessons 与有上限的索引。Cursor 适配器在读取
active task 时注入检索上下文，dsh 适配器在会话开始时注入。设计理由见 [Memory](study/memory/memory.md)，各策略的 owner 见
[Policies](../skills/README.md)。

关闭的 task 与旧交接笔记移到 `.agent-loop/archive/`。运行时证据在 `.harness/`，日志与产物有上限。必须比运行时保留期更久的
项目证据，放在项目自己的存储里。heartbeat 策略观察 detach 的作业，见 [Heartbeat](study/harness/heartbeat.md)。

## 可选的手机检查点

pager 是独立的包。Outlook / Graph 见 [tools/pager](../tools/pager/README.md)，飞书见
[Feishu setup](../tools/pager/docs/feishu.md)。在工作项目里配置 `.agent-loop/pager.json`。计划批准、reviewer 升级、
反复评审失败与预算耗尽都可以推送给 human。worker 必须保持运行才能等到回复；pager 无法重启已退出的 agent。

## 可选的按需 skill

环外的 skill 只在被点名时加载：在 Cursor 对话里输入 `/<skill-name>` 再接请求，或在消息里提到该 skill。列表见
[Policies](../skills/README.md) 的 *Explicit / cold policies*。例如把一个已关闭的研究 Goal 写成 arXiv 风格论文和短预告片：

```text
/research-to-paper Write wm_forge's conclusions as an arXiv paper, then make a 10 s teaser.
```

sync 脚本只把这些 skill 链接进 Cursor。Codex 看不到它们，需要让它去读 agent-loop 仓库里的 `skills/<skill-name>/SKILL.md`。

## 升级与卸载

切换 harness 版本前，完成或暂停进行中的工作，查看 changelog，并保存工作项目的状态与证据。v0.1 在没有明确迁移说明时，
先完成 active task 再切版本；不要假设任意运行时 schema 都能跨版本恢复。

在 harness 仓库里拉取 tags，检出选定版本，用同样的 `pip install` 命令重装；目录或 skill 有变化时重跑 Cursor sync 脚本，
然后重启 Cursor。它的 junction 直接指向仓库，所以切分支也会改变 hooks 使用的代码与策略。

卸载 Cursor 集成，在同一个仓库里运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-from-cursor.ps1
```

备份会保留，供手动恢复。重启 Cursor 以卸载 hooks。CLI 另外卸载：

```sh
python -m pip uninstall agent-loop
```

项目的 memory、计划、归档与实验证据属于项目，会继续保留。
