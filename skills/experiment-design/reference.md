# Reference

主流程见 [SKILL.md](SKILL.md)。这里放两次真实事故的逐项清单、低频操作的做法，以及正文按情形指过来的模板与细则。

前两节是**某个领域的实例，不是通用判据**——它们是 Phase 0 那道门与「先复现对方样例」
那条规则的由来。做同类工作时照着核，不同领域就只取教训、自己列清单。

---

## 一、问题本身不可解：Franka pick-cube

**事故**：cube 位置每 episode 随机化，却没有进 observation。10+ 组实验（DART、闭环 IK、
noise aug、history）全部 0% 成功率。**所有调优都是在一个不可解的问题上做无用功。**

策略学习场景下 Phase 0 的具体问法是 **`π(observation) → action` 是单值函数吗**，逐项核：

1. 决定 action 所需的信息，是否都在 observation 里。
2. 同一 observation 在不同 episode 下是否对应不同 action。是则问题不可解——
   **列出所有随机化变量**，确认它们要么被固定、要么进了 observation。
3. observation 的构成顺序，以及 action 语义（absolute / delta / target），
   在训练与评估两端是否一致。

不完备时三条出路：加进 observation（最直接）／固定该变量（只用于诊断）／
换 vision 等富信息模态（长期）。

监督学习、检索、预测类任务把 `observation → action` 换成 `输入 → 标签` 同样成立：
**决定标签的信息不在输入里，再调都是白费。**

---

## 二、契约不匹配：Cosmos3 `forward_dynamics`

**事故**：三发请求都返回 200，被记成「形状被接受」。实际是 7 维塞进要 10 维的 embodiment、
domain 名这份权重根本没训过、`num_frames=16` 被静默截成 13。样例就在已下载 checkpoint 的
`assets/` 里，跑一遍 3 分钟；没跑，两天的实验整批作废。

接入外部模型或服务时，在自己的输入上跑任何东西之前，先用**它自带的样例**跑通：
用它的输入、它的参数、它的参考输出，比到同量级。没有样例就跑它的 e2e 测试。

逐项对齐（序列/视频/策略模型的典型清单）：

| 项 | 要确认的 |
|---|---|
| 维数与排布 | 每一维是什么，顺序是 NCHW 还是 NHWC，batch 在不在第 0 维 |
| 单位与取值域 | 是否归一化，增量还是绝对值，角度用弧度还是度 |
| 枚举名 | 传进去的 domain / embodiment / task 名，**这份权重真的训过吗** |
| 时间轴 | 帧数、chunk 大小、fps，是否会被静默截断 |

**返回 200 不是判据。** 只校验 schema 的接口对语义不设防——维度对、名字合法、请求成功，
语义可以完全是错的。

**生成类结果先看产物，再算指标。** 标量分不出「不准」与「根本没在预测」，
整幅画面的差分也分不出「主体在动」与「背景在抖」。

---

## 三、归档与冻结的做法

`features/<feature>.md` 在 feature 冻结时按 `project-docs`「冻结」改为 as-built，不删除、不搬。在文档顶部加：

```markdown
> Status: as-built (frozen YYYY-MM)。最新设计以 <活文档> 为准。
```

之后该文档只读。耐久的 rationale 上提到活文档，feature 文档退化为「链接活文档 + 保留设计与脉络」，实验证据留在同名 exp。**partN / featureN 这类内部序号不外泄**——它们只在本仓库有意义。

---

## 四、实验设计模板

```markdown
## Exp-<ID>: <标题>
### 假设 / 决策价值
<一句话>；否定结果会改变: <什么>
### 领域先例（研究型假设必填）
- <已知结论 / 常用做法 / 坑 + 链接>；没找到写「未找到」及查了哪里
### 方案
- 脚本 / 关键参数 / 对照组 / 变量
### 预期与判据
- 成立: <metrics>　不成立: <metrics>　判据: 层 <n>
### 结果 / 分析 / 结论与 Next Step
（待实验）
```

## 五、run 输出与 Harness 指纹

Harness 指纹只含已跟踪改动和未被 gitignore 的未跟踪文件：文档目录在指纹内时，留在那里的 run 输出在 verifier
之后删除会让证据 stale；在 gitignore 里（如 `.agent-loop/`）时，verifier 之后改文档不会让证据 stale。

## 六、远端资产去留

本 task 在远端节点上建的资产逐项按三档定去留：Hot（节点清单 `hot_models` 里的基础模型）不清理；Warm（repo 专有 ckpt）
`-atime +7`，清理时 `! -name` 排除 Hot；Cold（`.venv` / `build` / `__pycache__` / pip cache）`-mtime +3`。一次性的删除，
要留的把路径与用途写进 `facts.md`。公共节点上不用 `docker image prune -a`、`docker system prune -a`、`docker image rm <tag>`。
