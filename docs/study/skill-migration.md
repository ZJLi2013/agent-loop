# 七个按需 skill 的迁出清单

> [Study 索引](README.md) · 发行专题。范围依据在 [design.md 的范围](../../design.md#范围)，弃用与同名规则在
> [安装 skill 包](../usage.md#skill-packs)，发行告知在 [CHANGELOG 的 Deprecated](../../CHANGELOG.md#deprecated)。
> 盘点基于 2026-10-30 的 `main`。

## 结论

七个按需 skill 在含弃用说明的版本发行之后迁出到维护者的私有 pack，本版本照常提供与维护。它们都不声明 `requires`，
也没有别的 skill 用 `requires` 依赖它们；迁出前要改的是核心里点名它们的四个文件、公开文档里的两处，以及安装测试里借用
`gen-ppt` 当夹具名的用例。核心不装任何 pack 也能完成 task 生命周期：七个都不在生命周期里，唯一被核心借用的方法
（`experiment-design` 的领域先例查法）已经写在核心自己的正文里。

## 为什么迁出，为什么是私有 pack

[范围](../../design.md#范围)只收三类公开保证：task 生命周期、让它在宿主上成立的安装与接线、本仓库自己的发行与贡献。
这七个都是被点名才加载的写作、评审与作图方法，不参与任何准入、执行或验证，属于「理由只是放得进某个 skill」
或「依赖个人风格」的输入，处置是转外部 pack；已发行的先标弃用、保留一个版本再删。

目标选维护者的私有 pack，不另拆公开 pack：agent-loop 当前没有外部使用者（没有 fork、外部 issue 或 PR），
公开拆包没有读者。**推翻条件**：出现 fork、外部 issue 或外部 PR 时，按可见性拆出一个公开 pack，私有 pack 只留个人内容。
公开用户的迁移路径不依赖私有 pack：从本版本复制 `skills/<name>` 进自己的 pack 并登记，见 [CHANGELOG](../../CHANGELOG.md#deprecated)。

## 逐项清单

| 公开名 / 现有路径 | 资源文件 | 用途与范围依据 | 依赖 | 迁出时要改的核心与公开文档 |
|---|---|---|---|---|
| `code-review` / `skills/code-review/` | `reference.md` | 审 PR 或 diff 的输出格式与严重度；评审方法，不是生命周期 | 无 `requires`；正文点名七项内的 `upstream-contribute` | `rules/agent-loop.mdc` 环外能力一行；`skills/README.md` 冷 policy 列表 |
| `code-to-kernel-diagram` / `skills/code-to-kernel-diagram/` | `example.md`、`mla_kernel_sample.jpg` | 把模块画成 kernel 数据流图；作图方法 | 无 | `rules/agent-loop.mdc`；`skills/README.md` |
| `code-to-uml-diagram` / `skills/code-to-uml-diagram/` | 无 | 类图与时序图；作图方法，[#46](https://github.com/ZJLi2013/agent-loop/issues/46) 已按「没有 owner」判为转外部 pack | 无 | `rules/agent-loop.mdc`；`skills/README.md` |
| `gen-ppt` / `skills/gen-ppt/` | `STYLE.md`、`scripts/ppt_style.py` | 生成 16:9 PPT；个人样式 | 无 | `skills/README.md`；`tests/test_install_skills.py` 用它当「agent-loop 自己的 skill」夹具名，改用一个核心 skill 名 |
| `research-to-blog` / `skills/research-to-blog/` | 无 | 调研写成对外博客；写作方法与个人风格 | 无；被核心点名 | `rules/agent-loop.mdc`；`skills/README.md`；`skills/experiment-design/SKILL.md` 第 123 行「查法沿用 `research-to-blog` 的 Phase 1」删去指针，同一句已写明查法 |
| `research-to-paper` / `skills/research-to-paper/` | 无 | 实验写成 arXiv 稿与短片；写作方法 | 无 | `rules/agent-loop.mdc`；`skills/README.md`；`docs/usage.md`「可选的按需 skill」一节的示例与 `docs/quickstart.md` 第 74 行改为指向 pack |
| `upstream-contribute` / `skills/upstream-contribute/` | 无 | 判断提 PR / Issue 并起草正文；贡献方法 | 无；被核心点名 | `rules/agent-loop.mdc`；`skills/README.md`；`skills/self-report/SKILL.md` 第 12 行的边界指针改为「他人仓库的 PR / Issue 不归本 skill」 |

七项之间只有一处点名（`code-review` → `upstream-contribute`），会一起迁走。迁出不改任何 skill 名，`requires` 接口不变。

## 核心独立运行要保留的责任

- `rules/agent-loop.mdc` 的「环外能力」一节点名其中六个；核心不点名任何包内 skill，迁出时整节删去，不换成 pack 名。
- `experiment-design` 研究型假设先查领域先例：查法（综述优先、「已开源 / 已解决」联网核实）留在核心，只删出处指针。
- `self-report` 只需说明他人仓库的贡献不在它的范围内，不需要知道谁负责。
- `skills/README.md` 的 *Explicit / cold policies* 一节与 `docs/usage.md` 的「可选的按需 skill」一节改为说明按需 skill
  由 pack 提供、怎样登记。

## 不在本清单内

- `remote-exec`：依赖个人节点池，已单独标弃用，删除与同名登记另做。`remote-exec` 正文点名 `upstream-contribute`，两者都迁出，不留在核心。
- 个人 rule：`rules/write-for-humans.mdc` 与 `rules/external-output-boundary.mdc` 点名 `research-to-blog` 与 `upstream-contribute`；
  这两条 rule 的去留随通用个人 rule 的迁出一起定，这里只记点名关系。
- CHANGELOG 里提到这些名字的旧条目是发行史，不改。

## 发行安排

1. 本版本：七项照常提供与维护，CHANGELOG 公告弃用。私有 pack 不登记同名 skill：同一名字同时有两个提供者时，安装器跳过包里那份并以非零退出。
2. 含弃用说明的版本发行后：删除 `skills/<name>`；按上表改核心与公开文档；私有 pack 以同名登记；重跑安装器，旧链接一次切到 pack。
