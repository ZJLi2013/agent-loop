# autoresearch 的循环

> 读的是 [karpathy/autoresearch](https://github.com/karpathy/autoresearch) @ `228791f`（2026-03）。
> 只看控制结构，不看 train.py 的训练细节。
> 专题导航见 [Study 索引](README.md)。2026-10-12 按当前本库架构修正对照，外部细节仍按上述版本理解。

## 结论

**它把状态放在 git 上，把验收交给一份指令要求 agent 不修改的脚本，然后禁止停。** 没有调度器代码——
整个循环是 `program.md` 里的一段散文，加上 git 提供的 checkpoint / rollback。

```text
                    ┌─────────────── LOOP FOREVER ───────────────┐
git state ─► 改 train.py ─► commit ─► 跑 5 分钟 ─► grep val_bpb ─┤
                                                                 │
                                    改善 → 留下 commit（advance）─┤
                                    没改善 → git reset（discard）─┤
                                    崩了 → 记 crash，revert ──────┘
                                              ↑
                                  results.tsv（刻意不进 git）
```

## 三个决定撑起了它，都不在 Python 里

**判据由约定不修改的评估代码给出。** 指令将 `prepare.py` 列为只读，`evaluate_bpb` 是 ground truth，时间预算
固定 5 分钟。这是指令边界，不等于文件权限或独立 runner 的强制隔离。「这次到底有没有变好」不由 agent 声称——它只能 `grep "^val_bpb:"` 然后和上一个
commit 比大小。相同硬件与评估条件下，固定预算让不同改动（模型大小、batch、架构）可比；不直接跨硬件比较。

**git 就是 checkpoint 与 rollback。** 没有 `task.md`，当前状态就是分支所在的 commit；接受一次
改动等于让分支前进，拒绝等于 `git reset` 回去。不另造机制，直接用版本控制。

**记录刻意留在 git 之外。** `program.md` 明确要求 `results.tsv` 不提交。效果是它能活过
`git reset`——代码回滚了，但「试过什么、得到什么数、为什么丢掉」这一行留下来。

## 失败是输入，不是终止条件

| 失败 | 处置 |
|---|---|
| 手误级（typo、缺 import） | 就地修，重跑；几次修不好就放弃这个想法 |
| 想法本身坏掉 | `status=crash` 记一行，换下一个 |
| 超过 10 分钟 | kill，当失败 discard |

最硬的一条是 `NEVER STOP`：不许问「要继续吗」「这是个好的停点吗」。理由写得很直白——人可能
在睡觉，5 分钟一轮，一夜大约 100 次实验。想不出点子时的处方是「think harder」：读代码里引用的
论文、重读 in-scope 文件、组合之前的 near-miss、试更激进的架构改动。

## 与本库的结构差异

| | autoresearch | agent-loop |
|---|---|---|
| 状态 | git 分支 + commit | plan + `task.md`；`.harness/state.json` 保存运行状态 |
| 验收 | 约定只读脚本给出的 val_bpb | 项目提供锁定 verifier；fingerprint 检查证据有效性，配置 reviewer 时另审解释 |
| 回滚 | `git reset` | 复用 git，不自动覆盖用户工作树 |
| 停止 | 只有人打断 | 中止清单 + 预算 |
| 规划 | 没有。不拆任务，不排优先级 | PLAN / SELECT 两格 |
| 记忆 | `results.tsv` 一行一次实验 | `facts` / `episodes` / `lessons` |

**它的接受规则是贪心的，这是最结构性的限制**：每一步都必须当场改善 val_bpb，否则被 reset。
所有「要连着改三处才见效」的想法都被排除——前两步还没回本就已经被丢掉了。`program.md` 允许
rewind 回更早的点，但要求「very very sparingly (if ever)」，所以搜索基本是单点爬山。

其余缺口：没有 PLAN，假设只留一行 description，没有轮数或机时上限（设计上就是跑到人打断）。

## 可以拿走的

- **将项目验收与执行过程分离**：本库已用锁定 verifier 与 evidence fingerprint 落地相关机制。
- **用 git 当 checkpoint / rollback**，不自造状态机。
- **否定结果的记录必须活过回滚**：放在被版本控制之外，或放在不会被 reset 的文件里。
- **区分实验对象与工作方法**：默认 agent 迭代 `train.py`，人维护 `program.md`。后者可类比本库
  rules / skills，但不意味着原项目已自动优化自己的工作方法；范围判断见 [业界实践](industry-practices.md)。
