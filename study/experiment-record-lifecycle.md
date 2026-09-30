# 实验记录的生命周期

> t9 于 2026-10-01 落地：Policy 定义完整生命周期；配置 reviewer 时，Harness 在有效决策落盘前
> 自动归档 closed task，并拒绝没有关闭当前 task 的 reviewer 决策。

## 结论

实验记录不应靠反复摘要来控制体量，而应分成三层：**活跃决策面、可检索索引、不可变原始证据**。
task 关闭时把多轮实验提升为一个决策，旧记录转为 `promoted / superseded / archived`；只有仍会改变
后续选择的结论留在活跃文档。行数上限只负责报警，不能代替生命周期。

当前规则已经覆盖单轮写回和 memory 晋升，但没有统一规定实验、交接记录和已完成 task 何时退出
活跃工作集。结果是内容虽然下沉到 Experiment Log、sub-exp 或 memory，跨 session 仍持续增长。

## 改造前缺口

现有 owner 分工基本正确：

- `experiment-design` 清理单轮草稿，把实验压成一行摘要；
- `work-planning` 把关键 evidence 提升到 plan document 的「当前结论」；
- `agent-memory` 保留未来还要检索的结论、否决项与教训；
- `task-state` 维护 task 与跨 session 交接。

缺的是这些对象的退役规则：

| 对象 | 当前写法 | 缺口 |
|---|---|---|
| Experiment Log | 每轮追加一行 | task 关闭后仍全部留在活跃 plan |
| sub-exp | 详细记录下沉 | 只移动体量，没有退出活跃索引 |
| `task.md` | done 行继续保留 | 每次 SELECT 都重新加载历史 task |
| `progress.md` | 按 session 追加 | 旧交接信息会遮蔽当前接手点 |
| `episodes.md#experiments` | task 完成后追加 | Goal 关闭后的剪枝仍靠人工 |

因此问题不是“摘要还不够短”，而是**摘要完成后原记录没有改变生命周期**。

## 开源实践里的共同结构

### DVC：实验默认不进入正式历史

[DVC Experiments](https://doc.dvc.org/user-guide/experiment-management) 把临时实验放在独立的
`refs/exps`，不让每次尝试变成普通 branch 或 commit。选中的实验才通过 `exp apply` 或
`exp branch` 提升；其余可以用
[`dvc exp remove`](https://doc.dvc.org/command-reference/exp/remove) 删除，再由
[`dvc gc`](https://doc.dvc.org/command-reference/gc) 清理不再被引用的 artifacts。

可复用的不是 DVC 命令，而是 **trial 与 promoted result 分层**：跑过不等于进入项目主线。

### MLflow：子 run 留证据，父 run 留最佳结论

[MLflow Parent/Child Runs](https://mlflow.org/docs/latest/ml/traditional-ml/tutorials/hyperparameter-tuning/part1-child-runs/)
用 child runs 保存参数、指标和 artifacts，parent run 只记录这一组尝试的最佳条件与汇总指标。
run 通过 tags 检索，并有 active / deleted lifecycle。

对应到文档：单轮实验是 child，task 是 parent；task 关闭后，活跃 plan 只需要 parent 级结论。

### MADR：历史不改写，但必须标明是否仍有效

[MADR](https://adr.github.io/madr/) 用 `proposed / accepted / rejected / deprecated /
superseded by ...` 表示决策状态。旧决定仍可追溯，但当前索引只需指向仍然有效的决定。

对应到实验：否定结果不该消失；被新证据覆盖的结论也不该继续以“当前事实”的身份出现。

## 适合 agent-loop 的模型

```text
当前结论 + 下一步决策                    ← 每轮可能加载
        │ promote / supersede
active Experiment Log（只放未闭合决策）  ← 当前 task 使用
        │ task CLOSE
archive index（一项 task 一个结论）       ← 定向检索
        │ evidence link
sub-exp / runs / artifacts               ← 原始证据，不自动加载
```

每条实验摘要使用以下状态之一：

- `active`：仍可能改变当前 task 的下一步；
- `promoted`：结论已进入稳定头部或项目文档；
- `superseded by Exp-X`：被更新证据替代；
- `rejected / disproved`：否定发现，提炼后进入长期 memory；
- `archived`：只承担追溯，不参与日常决策。

## 触发点

### Experiment CLOSE

`experiment-design` 只负责本轮：

1. 写一句结论与最多三条关键 evidence；
2. 删除设计阶段的过渡内容；
3. 把原始输出链接到 run / artifact；
4. 更新一行 Experiment Log。

### Task CLOSE

`work-planning` 负责跨轮 consolidation：

1. 把该 task 的多个 experiment 合并成一个 task 结论；
2. 更新「当前结论」与下一步决策；
3. 将相关实验标记为 `promoted / superseded / archived`；
4. 把详细行移出 active Experiment Log，只留一个 archive 指针；
5. 通知 `agent-memory` 写入仍会影响未来决策的结论或否决项。

### Goal CLOSE 或 pivot

1. plan document 冻结为 as-built；
2. `task.md` 的 done 行移入归档，只保留仍可执行或被阻塞的行；
3. `progress.md` 归档，活跃文件改为当前接手快照；
4. `episodes.md#experiments` 删除已由项目文档承接的重复摘要；
5. `disproved / rejected` 继续保留，除非已被更强决定明确 supersede。

阈值只作漏执行保护：例如 active Experiment Log 超过 10 行、done task 超过 5 行或
`progress.md` 出现第二个已失效接手点时，要求先 consolidation。真正触发仍是 task / Goal 转换，
不是定期让模型“看看能不能再总结”。

## Owner

不新增 consolidation skill：

- 单轮内容质量归 `experiment-design`；
- task / Goal 文档生命周期归 `work-planning`；
- 活跃 task 与交接快照归 `task-state`；
- 长期可检索结论归 `agent-memory`。

agent-loop 自身的长期迭代暴露了这些缺口，见
[`case_study/agent-loop-record-growth.md`](../case_study/agent-loop-record-growth.md)。

## 落地边界

- reviewer 模式：`harness/records.py` 在 task-boundary review 后机械移动 `✅ done / ❌ dropped`
  行；当前 task 没有进入 archive 时，review decision 无效并计入重试。
- single-agent 模式：CLOSE 仍由 `work-planning` 与 `task-state` Policy 执行；Harness 不在 verify
  前擅自修改工作文档。
- Experiment Log 与 memory 的提炼包含语义判断，不能用 markdown parser 自动完成；它们由 owner
  skill 执行，阈值只负责暴露漏执行。
