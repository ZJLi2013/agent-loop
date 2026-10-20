# Case：harness_vla image_delivery 在 CLOSE 后残留的 run 输出

> 观察于 2026-10-20，harness_vla `image_delivery` Goal 决策 stop、CLOSE self-audit 完成之后。

## 结论

CLOSE self-audit 按 `experiment-design` 的字面执行了，实验文档目录里仍留着 376 个文件、98 MB 的
run 输出。缺口在规则：「原始输出与日志保留」没有给出原始与中间的判据、保存位置和保留期限，又和
「原始 run、artifact 不可变」叠加，结果是**一次 run 写出的东西，只要不是图片，就都算原始输出，
永久留在实验文档旁边**。

结论实际只依赖 8 对 episode 的两个数：`states.json` 末步的 `terminated` 与事件流最后一条
`input_tokens`。它们的汇总表 `img_ab/summary_report.txt` 只有 3.6 KB；其余内容在 verifier 与
reviewer 读完后没有任何消费者。同仓库 `memory_layer`、`recipe_ablation` 两个实验目录同样形态，
连同 `image_delivery` 共约 360 MB。

## 现场

`harness_vla/exps/image_delivery/` 在 CLOSE 后的内容：

| 类别 | 文件数 | 体量 | 结论是否读它 |
|---|---:|---:|---|
| Codex 事件流 `*.stream.jsonl` | 10 | 96.2 MB | 只读最后一条 token usage |
| 逐步观测 metadata `*_metadata.json/NN.json` | 268 | 0.28 MB | 否 |
| `states.json`、transcript、audit、recipe | 35 | 0.43 MB | 只读 `states.json` 末步 |
| 日志、Codex 文本输出、prompt 样例 | 54 | 0.85 MB | prompt 样例被 img-impl verifier 引用 |
| 文档、review、上游草稿 | 9 | 0.03 MB | 是 |

另外三点：

- `img_ab_compact60k/`（30.8 MB）在实验文档里写明「不计入」，仍然保留。
- 实验文档写「逐格数据见 `img_ab/summary_report.txt`」，逐格表只存在于 run 目录里。直接删 run 目录，
  逐格数据会一起丢失；规则没有要求删除前先把它写进文档。
- 96 MB 的事件流和日志被 `.gitignore` 的 `*.jsonl` 挡住，没有进 git；其余 330 个 json / txt 一直
  以 untracked 状态挂在 `git status` 里，一次 `git add -A` 就会提交。

## agent 的分法合规，但与结论无关

agent 删了 png / npz，理由是「工具运行时的中间产物」；留下 json / log，理由是「原始输出与日志保留」。
规则只写了这两个词，没有判据，agent 就按文件类型划线。

这条线和结论无关：被删的逐步观测图和被留的逐步 metadata 是同一类东西，都是每一步的观测快照，
结论都不读；结论真正读的两个字段，则和 96 MB 的完整事件流一起被「保留」。

## 规则缺口

| 缺什么 | 现状 | 后果 |
|---|---|---|
| 判据 | `experiment-design` Phase 3 第 3 条：「一次性脚本与中间文件删除（原始输出与日志保留）」 | 按文件类型划线，run 写出的大部分东西都能归为「原始输出」 |
| 位置 | `design.md`、`work-planning`、`experiment-design` Phase 4 都写「原始 run、artifact 不删 / 不可变」，没说放在哪 | 从远端拉回的 run 目录落在 plan document 同目录，CLOSE 回读未跟踪文件时把它们当作「规则要求保留」跳过 |
| 期限 | 没区分「verifier / reviewer 还要读」与「task 已 CLOSE」 | 本例 reviewer（记录 `20261020T103106Z-845f5d55`）逐条重解析过 8 对 `states.json` 与事件流，在那之前保留是对的；之后没有消费者，规则仍要求保留 |
| 提炼 | CLOSE 只要求「把原始输出链接到 run / artifact」 | 文档把证据指向 run 目录，反过来让 run 目录删不掉 |

[实验记录的生命周期](../docs/study/memory/experiment-record-lifecycle.md) 里的「不可变原始证据」
来自 DVC / MLflow，它们都有独立于工作文档的 artifact store。agent-loop 对 detach 的远端 GPU run 没有
对应的 store：Harness artifacts 按 `max_artifacts` 只留最近 20 次（见
[Plan growth](robojev-plan-growth.md)），于是 run 输出被拉回实验文档目录，「不可变」退化成「本地永久保留」。

## 修复

只改 Policy 文本，规则只在 `experiment-design` 的 CLOSE self-audit 定义一次，跟踪见
[#48](https://github.com/ZJLi2013/agent-loop/issues/48)：

- **run 输出不放在实验文档目录。** 结论、verifier 与 reviewer 要读的数据写成文档里每个 run 一行的表；
  run 目录留在远端或仓库外 / 被 gitignore 的 scratch 目录，文档只写路径与复现入口。
- **run 目录在 task CLOSE 时删除。** 时机归 `work-planning`：reviewer 决定落盘后，未配置 reviewer 时
  verifier 通过后。sub-exp 仍不可变；远端也不保留副本，需要时按复现入口重跑。
- **结论标明不计入的 run 在 self-audit 时直接删除。**
- `design.md` 与 lifecycle 文档不再承诺「原始 run、artifact 不删」，只指向 `experiment-design`。

不能只补一句「CLOSE 后删除」：`harness/fingerprint.py` 对未跟踪文件取哈希，run 输出留在实验文档目录里，
verifier 之后再删就会让证据 stale。所以规则先规定位置，删除才不碰指纹。
