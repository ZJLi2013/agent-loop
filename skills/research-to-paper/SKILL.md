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
