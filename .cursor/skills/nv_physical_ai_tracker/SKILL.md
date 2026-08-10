---
name: nv-physical-ai-tracker
description: Track and summarize recent NVIDIA Physical AI items from NVIDIA Blog, NVIDIA Technical Blog, NVIDIA Research, and NVLabs. Use when the user asks for NVIDIA Physical AI, embodied robotics, Isaac, Cosmos, GR00T, synthetic data, simulation pipelines, 3DGS, diffusion/world models, or recent NVIDIA robotics research updates.
disable-model-invocation: true
---

# NVIDIA Physical AI Tracker

追踪 NVIDIA 在 embodied robotics / physical AI 上的新进展。**要的是简洁综述，不是逐篇论文笔记；
落点始终是「机器人工作流里什么变了」，不是产品宣传语。**

## 收什么

**收**：具身机器人 / 人形 / 操作 / 移动机器人 / 工业视觉；合成数据、sim2real、数字孪生、
数据工厂、轨迹生成、策略训练与评估；physical AI 的基础模型与领域模型（Cosmos、Isaac GR00T、
VLA/VLM/action model、world model、生成式视频、3D/4D 场景生成、3DGS、神经重建）；
实质影响这套工作流的平台（Isaac Sim / Lab / Lab Arena、Omniverse/OpenUSD、OSMO、Jetson Thor、
DGX/RTX PRO）。

**不收**：不改变训练/仿真/部署流程的纯硬件发布；与物理 AI 无关的 LLM / 企业 AI / 游戏 /
数据中心 / 财经消息；第三方评论（除非有助于解读官方条目）。

## 源与检索

官方源优先：[NVIDIA Blog](https://blogs.nvidia.com/blog/)、
[Technical Blog](https://developer.nvidia.com/blog/)、[NVIDIA Research](https://research.nvidia.com/)、
[Research Labs](https://research.nvidia.com/labs/) 与 [NVLabs](https://nvlabs.github.io/)。
GitHub / Hugging Face 只在官方条目引用时跟进。

```text
site:blogs.nvidia.com/blog physical AI robotics Cosmos Isaac GR00T synthetic data
site:developer.nvidia.com/blog physical AI Isaac Sim Isaac Lab Cosmos GR00T
site:research.nvidia.com embodied AI robotics 3D Gaussian Splatting diffusion world model
site:nvlabs.github.io robotics 3DGS diffusion embodied AI
```

复现锚点（搜索时的常驻关键词）：Cosmos 世界基础模型、Isaac GR00T / GR00T-Dreams、
Isaac Sim / Lab / Lab Arena、Omniverse / OpenUSD / NuRec 神经重建、physical AI agent skills
与 launchables、3DGS/4D 场景方法、agentic 3D world generation。

## 流程

用户没指定时间窗就取最近 1–3 个月。搜索 → 只留有明确 physical AI 关联的 → 跨 Blog/Research/GitHub/HF
去重 → 按下面的 tag 分类（一个主 tag + 可选副 tag）→ 写中文摘要 → 归纳 3–5 条趋势。

**Tags**：`world-model`（Cosmos、视频生成、未来状态预测）、`robot-foundation-model`（GR00T、VLA、策略模型）、
`synthetic-data`、`sim2real`（Isaac Sim/Lab、数字孪生、策略评估）、`3d-reconstruction`（3DGS/4DGS、OpenUSD 采集）、
`pipeline`（OSMO、数据工厂、端到端流程）、`dataset`、`edge-deploy`（Jetson、机器人端推理）、
`vision-ai`（有物理落地的工业检测 / 视频 AI）。

## 输出格式

```markdown
# NVIDIA Physical AI Tracker - [时间窗]

## TL;DR
[3-5 条主方向]

## Key Updates
### [Title]
- Source / Link / Tags: `tag-1`, `tag-2`
- Why it matters: [1-2 句中文，说机器人工作流里什么变了]

## Trend Readout
- [主题 1–3，各一句解读]

## Watch Next
- [下一步方向、待解问题或要盯的源]
```

## 当前底图（mid-2026）

整条栈在收敛：`Cosmos` 供世界建模与合成数据 → `Isaac GR00T` 把真实/遥操/合成数据变成策略 →
`Omniverse`/`OpenUSD`/`Isaac Sim`/`Isaac Lab` 供仿真、孪生与评估 → `OSMO` 与 agent skills
把这套变成可复用流水线；`3DGS`/神经重建与生成式 3D 世界是从真实传感数据进仿真的桥。
新条目按它落在这条链的哪一环来定位。
