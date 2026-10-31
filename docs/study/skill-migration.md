# 按需 skill 与通用 rule 的迁出清单

> [Study 索引](README.md) · 发行专题。范围依据在 [design.md 的范围](../../design.md#范围)，同名规则在
> [安装 skill 包](../usage.md#skill-packs)，发行告知在 [CHANGELOG 的 Removed](../../CHANGELOG.md#removed)。
> 盘点基于 2026-10-30 的 `main`。

## 结论

七个 skill（`remote-exec` 与六个按需 skill）和两条通用 rule（`code-hygiene`、`shell-exec`）已从 agent-loop 删除，
由维护者的私有 pack 以同名提供；重跑安装器后链接一次切到 pack。它们都不声明 `requires`，核心 skill 也不依赖它们；
包里的 skill 仍可按公开名 `requires` 它们。核心不装任何 pack 也能完成 task 生命周期：这些都不在生命周期里，唯一被核心借用的方法
（`experiment-design` 的领域先例查法）写在核心自己的正文里。

`code-to-uml-diagram` 原在清单内，[#125](https://github.com/ZJLi2013/agent-loop/issues/125) 把它接进 `work-planning`
第 2 步的类级设计，成为生命周期的一步，留在核心。

## 为什么迁出，为什么是私有 pack

[范围](../../design.md#范围)只收三类公开保证：task 生命周期、让它在宿主上成立的安装与接线、本仓库自己的发行与贡献。
这些都是被点名才加载的写作、评审与作图方法，或依赖个人节点池与个人习惯，不参与任何准入、执行或验证，处置是转外部 pack。

目标选维护者的私有 pack，不另拆公开 pack：agent-loop 当前没有外部使用者（没有 fork、外部 issue 或 PR），
公开拆包没有读者，也不保留弃用窗口。**推翻条件**：出现 fork、外部 issue 或外部 PR 时，按可见性拆出一个公开 pack，
私有 pack 只留个人内容。

## 逐项清单

| 公开名 | 资源文件 | 用途与范围依据 | 核心里删掉的点名 |
|---|---|---|---|
| `remote-exec` | `reference.md`、`scripts/` | 远端 GPU 执行；依赖个人节点池，节点清单随包放在包根的 `configs/` | 核心 rule 与 skill 早已不路由到它 |
| `code-review` | `reference.md` | 审 PR 或 diff；评审方法 | `rules/agent-loop.mdc` 环外能力一节；`skills/README.md` 冷 policy 一节 |
| `code-to-kernel-diagram` | `example.md`、`mla_kernel_sample.jpg` | kernel 数据流图；作图方法 | 同上 |
| `gen-ppt` | `STYLE.md`、`scripts/ppt_style.py` | 16:9 PPT；个人样式 | `skills/README.md`；安装测试的夹具名改用 `code-to-uml-diagram` |
| `research-to-blog` | 无 | 对外博客；写作方法 | 同上两处；`experiment-design` 的查法出处指针；`write-for-humans`、`external-output-boundary` 的指针 |
| `research-to-paper` | 无 | arXiv 稿与短片；写作方法 | 同上两处；`docs/usage.md`「可选的按需 skill」一节与 `docs/quickstart.md` 改为指向 pack |
| `upstream-contribute` | 无 | 提 PR / Issue；贡献方法 | 同上两处；`self-report` 的边界句；`external-output-boundary` 的模板指针 |
| `code-hygiene`（rule） | 无 | 注释与 commit message 风格；个人习惯 | 无 |
| `shell-exec`（rule） | 无 | 多行命令与 PowerShell 的坑；个人环境 | 无 |

迁出不改任何名字，`requires` 接口不变。CHANGELOG 里提到这些名字的旧条目是发行史，不改。

## 核心独立运行保留的责任

- `rules/agent-loop.mdc` 不点名任何包内 skill；「环外能力」一节整节删去，不换成 pack 名。
- `experiment-design` 研究型假设先查领域先例：查法（综述优先、「已开源 / 已解决」联网核实）留在核心。
- `self-report` 只说明他人仓库的贡献不在它的范围内，不说明谁负责。
- `docs/usage.md` 的「可选的按需 skill」一节说明按需 skill 由 pack 提供，指向[安装 skill 包](../usage.md#skill-packs)。
