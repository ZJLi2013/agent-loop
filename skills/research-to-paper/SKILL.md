---
name: research-to-paper
description: >-
  把已收口的研究实验写成 arXiv 风格的论文，可选用 onetake 做 5–15 s 对外短片。
  Use when turning experiments into an arXiv-style paper or technical report, or making a short
  teaser / promo video for one.
disable-model-invocation: true
---

# Research → Paper（实验到 arXiv 稿与短片）

**论文和短片里的每个数字都能回指到实验记录。** 先写内部的 `paper/claims.md`：一句话主张，
以及每个要出现的数字的值、条件、seed 数 / 样本量和来源。台账里没有的数字不出现。

- **素材从哪取**：plan 的「当前结论」、`exps/` 实验记录、`memory/episodes.md`、`archive/tasks.md`
  的 evidence 指针。主结论还有 `active` 实验时只写大纲。
- **否定结果进正文**：`disproved / rejected` 写进 Ablation 或 Limitations，不删。
- **短片只用真实产出**：rollout 帧、用论文同一份数据重建的曲线；不用文生图或生成视频。
  片中数字与论文同值、同条件。制作流程按 [onetake](https://github.com/feitangyuan/onetake) 自己的 SKILL.md。
- **onetake 是 PolyForm Noncommercial**：公司宣传等商业用途先停下问 user。
- 编译与渲染在远端节点跑，归 `remote-exec`；披露、型号脱敏与去私料归 `external-output-boundary` rule。

## onetake 实操

- **片长 10–15 s**：它的节奏规则（镜头长短差 ≥ 4×、留静止段）在 5 s 里撑不开。
- **远端容器**：`python:3.11-slim` + apt `ffmpeg nodejs` + pip `playwright opencv-python-headless brotli`
  + `playwright install --with-deps chromium`，约 10 分钟。12 s 的 1080p30 草稿 8 workers 3–7 分钟，深缩放最慢。
- **开场画面挑缩略尺寸下也读得出对比的那一帧**（WM 与仿真器同一时刻、瓶子立着 vs 躺着），读不出就换帧。
- **`__track` 一旦定义，probe 只跟这些 id**：只登记一两个元素会得到「0 个交接处、continuity 1.00」，不算证据。
  每个承接者都登记，每次 `seek` 先清空；只改 `__track` 不动画面时，拿旧草稿重跑 probe / verify，不重渲。
- **细线当不了承接者**：probe 不认 4 px 的分隔线；让它真的长出下一拍（轨迹压平收进标题横线），不靠加宽 box。
- **声音只有合成材质**（录音源不随仓库发布）；事件时间只在 comp 的 `__events()` 里写一份，导出后再配音。
- **三个概念可以都出草稿让 user 选**，看片定稿比读概念描述快；成片 `--final` 4K60 存档，网页另转 1080p60 `+faststart`。
