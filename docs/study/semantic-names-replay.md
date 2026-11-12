# 语义名与冻结后的 plan 目录：回放

> [Study 索引](README.md) · 被测措辞是 `work-planning` 的命名一句与主线交接的冻结段，以及 `task-state` 的示例，对应
> [#201](https://github.com/ZJLi2013/agent-loop/issues/201)。回放于 2026-11-12，改动前的对照基于 `34661d8`。

## 结论

冻结段改变了行为：Goal 刚完成时，改动前 worker 把 `plan-archive.md` 与 `sub-exp/` 留在 plan 目录里，改动后只留 plan document，
耐久结论进项目文档、否定发现进 memory 的 `rejected`，两样都没丢。命名一句没有改变行为：改动前 worker 已经用语义名，
这一句只是把现有做法写成规则，并让示例与它一致。Goal 未完成时，改动前后都不动 plan 目录。

| 场景 | 请求 | 改动前 | 改动后 |
|---|---|---|---|
| N 命名 | 「下一个 Goal：worker 的资产加载改成共享缓存，先做缓存格式、再做预热」 | 语义名（`shared-asset-cache` / `cache-format`） | 语义名（`worker-asset-cache` / `asset-cache-format`） |
| F 冻结 | 「scene-runtime 做完了，主线已标 done，按规则收尾」 | 留下 `plan-archive.md`、`sub-exp/probe.md` | 只剩 `plan.md`；否定发现在 `rejected`，1.8 s 结论在 `docs/runtime.md` |
| C 对照 | 「接着做 scene-runtime 的下一个 task」（Goal 未完成） | 四个文件都在 | 四个文件都在 |

## 输入

合成项目 sim：主线一个 Goal `scene-runtime`（单场景崩溃拖垮全部，改成每场景一个 worker 进程）。plan 目录有 `plan.md`、
`plan-archive.md`（一条耐久结论「worker 启动耗时 1.8 s，主要在资产加载」、一条否定发现「GPU 渲染放进 worker 显存翻倍，已否决」）、
`sub-exp/probe.md` 与 `run.log`；项目有被跟踪的 `docs/runtime.md` 与 `memory/episodes.md`（`rejected` 为空）。
F 的主线行是 `✅ done`；C 是 `▶ next`，plan 的当前结论写 worker 尚未上线；N 的主线行是 `✅ done`，human 给出下一个 Goal。

两侧只差 `work-planning` 与 `task-state` 两份 skill 原文。worker 是一次调用：Codex CLI 上的 gpt-6-astra（reasoning effort high），
workspace-write，直接改项目文件，请求只说工作需求，不提命名或冻结。每格 1 次，另有两侧各一次 F 冒烟。

## 判定

- N：新 plan 目录名与 task id 都含字母词、不是 `t3` / `s2` 这类序号，`rN` 仍是序号。
- F：plan 目录只剩 plan document；否定发现（GPU 与「翻倍」或「12 GB」）在 `rejected` 或 plan 头部；1.8 s 在 `docs/runtime.md` 或 plan 头部。
- C：四个文件都还在。

## 夹具修正

- 冒烟时 F 的判定要求字面「显存翻倍」，改动后一侧写的是「显存从 6 GB 增至 12 GB，翻倍」，被误判；判定改为上面的口径。
- N 的判定首版要求至少两个 task，两侧都只写了一个；`work-planning` 本来就只要求写最近 1–2 项，判定改为至少一个后重跑改动后一侧。
- C 首版夹具的当前结论写「每场景一个 worker 已上线」，正好满足主线退出条件，改动后一侧据此把 Goal 判为完成并冻结；
  这是夹具自相矛盾，改为 worker 尚未上线后重跑两侧。

## 解释边界

- 每格 1 次、一个模型、一个合成项目。
- N 两侧都已用语义名，这一格不能说明命名一句有作用，只说明它不会把 worker 推向别的做法。
- 合成项目不是 git 仓库，回放不覆盖 `leftovers` 对 `.agent-loop/` 外目录的处理；那部分由 `tests/test_records.py` 的真 git 夹具钉住。
