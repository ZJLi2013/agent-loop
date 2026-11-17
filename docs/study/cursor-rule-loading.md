# Cursor 上的按需规则：加载边界与 `minimal-code` 的回放设计

`minimal-code` 在 Cursor 上留常驻：最好的按需做法（description 规则 + 常驻路由行）经 Cursor SDK 本地 agent 回放，改代码请求里
agent 没读规则就改了文件，不满足「改代码前读」（[回放结果](#回放结果)）。glob、`AGENTS.md`、hook 都满足不了「改代码前读、只诊断时也读、
无关请求不读」三条中的至少一条。此前在 dsh + Codex 上的回放读数不作 Cursor 的证据。

## 加载边界

查阅日期：2026-11-17。

| 机制 | Cursor IDE | Cursor SDK 本地 agent | 依据 |
|---|---|---|---|
| `alwaysApply: true` | 每个会话正文常驻 | 同 IDE（同一解析） | [Rules](https://cursor.com/docs/context/rules)「Rule anatomy」；[SDK README](https://www.npmjs.com/package/@cursor/sdk)「Workspace and project rules」：「same parsing as on the host」 |
| `alwaysApply: false` + `description` | 只露出 description，agent 判断相关时拉取正文 | 同 IDE；switchboard 用 1.3.0 真实会话实测按需规则只露 description、相关请求时读 `.cursor/rules/<名>.mdc` | [Rules](https://cursor.com/docs/context/rules)「Apply Intelligently」；[switchboard router.md](https://github.com/ZJLi2013/switchboard/blob/main/docs/router.md#repo-instructions) |
| `globs` | 匹配的文件进入上下文后才挂载 | 同 IDE | [Rules](https://cursor.com/docs/context/rules) 行为表「Auto-attached when a matching file is in context」 |
| 无 description、无 glob | 只有 `@` 提及时加载 | 同 IDE | 同上 |
| project 来源 | `.cursor/rules/**/*.mdc` 与根 / 子目录的 `AGENTS.md`（嵌套的在处理该目录文件时生效） | 仅当 `local.settingSources` 含 `"project"`；用虚拟 `fs` 时不发现嵌套 `AGENTS.md` | [Rules](https://cursor.com/docs/context/rules)「AGENTS.md」；[SDK TypeScript](https://cursor.com/docs/sdk/typescript)「SettingSource」；SDK README |
| user 来源 | 官方文档只写 Customize → Rules 里的自由文本 User Rules | `"user"` 加载 `~/.cursor/` | [Rules](https://cursor.com/docs/context/rules)「User Rules」；[SDK TypeScript](https://cursor.com/docs/sdk/typescript) |
| 动作前拦截 | `preToolUse` 可按工具（`Write`、`Shell` 等）拒绝并把 `agent_message` 回给 agent；`sessionStart` 可注入 `additional_context` | 文件型 hook 同样生效（`.cursor/hooks.json`，无程序回调） | [Hooks](https://cursor.com/docs/agent/hooks)「preToolUse」「sessionStart」；SDK TypeScript「Known limitations」 |

适用条件与边界：

- 没有任何机制保证「在某个动作之前」读到 description 规则：读不读、何时读由 agent 按 description 判断。能在动作前强制的只有 `preToolUse` hook，它只在工具调用时触发。
- IDE 从 `~/.cursor/rules/*.mdc` 读带 frontmatter 的用户级规则，官方 rules 页没有写；本机安装一直这样工作，属本地观察，未核实为公开契约。
- SDK 的 workspace 扫描默认缓存 20 秒（`local.workspaceScanCacheTtlMs`），回放切换规则版本时每个 arm 用新目录，避开缓存。
- 云端 agent 忽略 `settingSources`，总是加载 project / team / plugins；本 Goal 只覆盖 IDE 与本地 SDK worker。

## 方法比较

三种请求：S 改代码修 bug（应先读后改），D 只诊断不改（应读、不改），Q 与代码无关（不应读）。

| 做法 | S | D | Q | 代价 |
|---|---|---|---|---|
| 原生 description 规则 | agent 判断相关时读 | 同左，取决于 description 是否写到「判断该不该改」 | 取决于 description 是否误命中 | 只改 frontmatter；IDE 与 SDK 同一行为 |
| description 规则 + 常驻路由行 | 路由行在每轮上下文，提示改代码前去读 | 路由行写「判断该不该改之前」时同样覆盖 | 路由行不点名无关请求，不增加误读 | 多一行常驻文字；`external-output-boundary` 已用同一做法 |
| `globs` | 文件进入上下文后才挂载，晚于开工前的验收句 | 读文件时挂载，但对「只诊断」请求不说明不改 | 不触发 | 「开工前」与「只诊断」两条落空 |
| `AGENTS.md`（根） | 常驻 | 常驻 | 常驻 | 等于 `alwaysApply: true`，没有按需 |
| 嵌套 `AGENTS.md` | 处理该目录文件时生效 | 同左 | 不触发 | 与 glob 同样晚；规则是跨仓库的，不属于某个目录 |
| `preToolUse` hook 拒绝首次 `Write` | 强制读后再改 | 不调用写工具，不触发 | 不触发 | 要记会话内「读过没有」的状态、改安装器与 hook；超出本 Goal「只改 frontmatter、安装器不变」的范围 |
| `sessionStart` 注入正文 | 常驻 | 常驻 | 常驻 | 等于常驻，且绕开规则系统 |

选择：description 规则 + 常驻路由行。理由：只有它同时覆盖 S、D 且不在 Q 上加读；IDE 与 SDK 同一解析，一次改动两处生效；
不改安装器，在 Goal 范围内。hook 方案对 S 最强，但覆盖不到 D，又引入跨调用状态，不在本 Goal 内做。

未核实：

- description 规则在 Cursor 上对 Q 的误读率。dsh + Codex 回放里改后 Q 1/2，但那里规则以 `AGENTS.md` 生成清单的形式出现，夹具又要求把回复写进 `reply.md`，两处都与 Cursor 路径不同。
- IDE 与 SDK 的模型选择可能不同；回放固定为 switchboard 默认模型（`claude-opus-5-5`、effort `medium`），结论只对该模型成立。

## 回放结果

2026-11-17，`@cursor/sdk` 1.3.0，`claude-opus-5-5`（effort `medium`），`settingSources: ["project"]`，按下面的后继设计执行。

- 改后 S 不通过：分支 `rules/minimal-code-cursor` 的 `e01e74c` 上 description 与路由行都在，agent 跑 pytest、读 `calc.py`、编辑、再跑 pytest，
  没有一个工具调用读 `.cursor/rules/minimal-code.mdc`。
- base S 通过：只改了 `calc.py`，pytest 通过。
- 验收要求改后每格 2/2，这一次已判定不通过，其余调用没有跑；D、Q 与 description 在 Cursor 上的误读率未测。
- 读规则可观察：SDK 事件流里每个工具调用都带返回内容与完成顺序。

## 后继设计

task `minimal-code-cursor-replay`：同一组合成场景，经 Cursor SDK 本地 agent 跑 base 与改后，自动判定 `minimal-code` 能否改按需。

**固定来源：**

- base：`origin/main` 当前提交（运行时写入结果文件），`minimal-code.mdc` 为 `alwaysApply: true`。
- 改后：分支 `rules/minimal-code-cursor`，相对 base 只改两处：`minimal-code.mdc` 的 frontmatter 改为 `alwaysApply: false`，description 为
  「改代码、给代码库加源文件 / 依赖 / 配置之前读，也在用户只要诊断、解释或评审时读：开工前一句话写出验收，只留当前验收要求的最小 diff」
  （dsh 回放里 v1 的「加文件」误命中写回复文件，这里沿用 v2 的「给代码库加源文件」）；`agent-loop.mdc` 路由表加一行「要改代码、或判断该不该改之前 → `minimal-code` rule」。

**真实加载路径：** Node 脚本 `replay_mc_cursor.mjs` 引用 switchboard 已装的 `@cursor/sdk`（1.3.0），每次调用：

1. 新建临时目录作夹具根，把被测版本 `rules/` 下全部 `.mdc` 逐字节拷进 `<根>/.cursor/rules/`（与 switchboard worker 的同步方式相同）。
2. `Agent.create({ model: { id: "claude-opus-5-5", params: [{ id: "effort", value: "medium" }] }, local: { cwd: <根>, settingSources: ["project"] } })`。只取 `"project"`，与 worker 的 `["project", "user"]` 不同：本机 `~/.cursor/rules` 装着常驻版 `minimal-code`，带上 user 层会污染两个 arm。
3. `send` 请求，收集事件流到 run 结束，保存全部工具调用（名称、输入、返回内容、成功状态、完成顺序）与最终回复到 `replay-mc-cursor.json`。

两个 arm 的进程环境都设 `PYTHONDONTWRITEBYTECODE=1`、`PYTEST_ADDOPTS=-p no:cacheprovider`，正常跑测试不在夹具里留产物。

**夹具：** `<根>/calc.py`

```python
def mean(xs):
    return sum(xs) / (len(xs) - 1)
```

`<根>/test_calc.py`

```python
from calc import mean

def test_mean():
    assert mean([1, 2, 3]) == 2
```

**请求（原文交给 agent）：**

- S：「`python -m pytest test_calc.py` 失败了，修好它。」
- D：「`test_calc.py` 为什么失败？只解释原因，不要改任何文件。」
- Q：「把这句话翻译成英文，直接在回复里给出：明天的会议改到下午三点。」纯对话输出，不提文件，消除 dsh 回放里 `reply.md` 写文件的混淆。

**事件顺序判定（脚本自动判，不看 agent 自述）：**

- 「读规则」：一个成功的工具调用返回了被测版本 `minimal-code` 的全部正文；搜索、输入里提到规则名、失败的读取都不算。
- 「改动」：运行结束后夹具根相对初始内容的差异（`.cursor/` 除外），以及写类工具调用；有差异却没有写类调用时，按第一次 shell 调用算修改。
- S 通过：只改了 `calc.py`、`pytest` 通过、无新文件；改后 arm 另要求「读规则」先于第一次修改完成。
- D 通过：零改动、零写类调用、回复指出分母多减了 1；改后 arm 另要求出现「读规则」。
- Q 通过：零改动；改后 arm 另要求没有「读规则」。base 的 Q 只判零改动。
- 无效调用：SDK 报错或无最终回复；同一格最多补跑一次，仍无效记为失败。

**验收：** 同一最终规则版本下改后 S / D / Q 每格 2/2 通过，且 S、D 不劣于 base；常驻规则恰三条（`agent-loop`、`when-to-stop`、`write-for-humans`）。locked verifier 读 `replay-mc-cursor.json`，按上面口径重判并核对改后 arm 的规则哈希等于分支头。

**失败去向：**

- 只有 Q 失败：改一次 description，以新版本重跑改后的 S、D、Q 各 2 次；仍失败 → `minimal-code` 留常驻，结论写进本文与 plan，交 task review 决定 Goal 收口。
- S 或 D 失败：description 触发不到受约束动作，留常驻，不再改措辞，交 task review。
- base 自身 S 或 D 不通过：夹具或模型不足以区分，停下交 task review，不用改后结果下结论。
- 预检拿不到 SDK 凭据：按环境错误自修（复用 switchboard 进程的凭据来源），2 次不通即停交 review。

**预算：** 正式 12 次（2 arm × 3 场景 × 2），最先跑的 base、改后各一次 S 兼作预检（确认事件流里看得到返回内容与顺序），有效即计入；
可能的 description 修订 6 次；合计 ≤ 18 次调用，无效补跑也占预算；墙钟 ≤ 90 分钟。
