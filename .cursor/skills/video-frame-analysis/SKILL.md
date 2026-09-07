---
name: video-frame-analysis
description: >-
  从一个或多个 mp4 抽同步帧、直接"看图"得出结论的调试流程：用 ffmpeg 按帧号抽帧，
  用读图能力逐帧目视，拼 2×2/并排对比图，把观测落成可追溯结论。Use when a video
  (rendered rollout, sim replay, overlay/projection, screen recording, camera clip)
  is the evidence and you need to inspect it frame-by-frame, compare two videos
  (e.g. real-overlay vs sim-replay) at matched timestamps, or diagnose spatial /
  temporal misalignment from footage instead of guessing.
disable-model-invocation: true
---

# Video Frame Analysis

视频是证据时，**别靠脑补，直接抽帧看图**。核心：ffmpeg 按帧号抽帧 → 逐帧读图目视 → 拼对比图 → 观测落成可追溯结论。KISS，抽帧脚本一次性用完即删。

## 何时用
- 有渲染/回放/录屏/overlay 视频，要判断"对没对上、动作对不对、哪一帧开始出问题"。
- 要对比**两个视频**（如 真实叠加 overlay vs 仿真 replay、修改前 vs 修改后）在**同一时间点**的差异。
- 从画面诊断空间错位（偏移/穿模/悬浮）或时序错位（超前/滞后/丢帧）。

## 流程

### 1. 先探元信息（对齐的前提）
```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=nb_frames,r_frame_rate,width,height,duration \
  -of default=noprint_wrappers=1 IN.mp4
```
- 记下每个视频的 **帧数 / fps / 时长**。对比两个视频前，先想清楚**帧号怎么对齐**：
  - 同一 episode、同起点 → 直接按**帧号**对齐（即使 fps 不同，只要都从 t=0 起，帧号 i 近似同一时刻）。
  - fps 不同要精确对齐 → 用**时间戳** `-ss <sec>` 而非帧号。
  - 若一个视频少几帧（如 chunk 尾部裁掉）→ 记录 offset，别默认严格 1:1。

### 2. 抽同步帧（按帧号，均匀采样关键阶段）
```bash
# 单帧按帧号抽（注意 select 里逗号要转义 \, ）
for IDX in 0 60 120 180 240 296; do
  ffmpeg -v error -i IN.mp4 -vf "select=eq(n\,$IDX)" -vframes 1 out_$IDX.png
done
```
- 帧号要**覆盖关键阶段**（接近 / 接触 / 保持 / 释放），不要只看首尾。
- 抽到临时目录（`$TMP`/`/tmp`），**用完即删**，不污染仓库。

### 3. 逐帧读图目视
- 用读图能力**逐张看**，对每帧写一句观测（谁在哪、对没对上、和上一帧比怎么变）。
- 看**相对关系**而非绝对像素：A 相对 B 偏左/偏右/有缝/重叠；是否恒定偏置 vs 随帧漂移。
- 找**系统性**信号：某方向的一致偏移 = 刚体/标定问题；随时间增长 = 累积漂移/scale；突变 = 某帧事件。

### 4. 拼对比图（给人看 + 落档）
```bash
# 2×2：上排 A 的两帧、下排 B 的两帧，缩放到同宽再 stack
ffmpeg -v error -i A_120.png -i A_240.png -i B_120.png -i B_240.png \
  -filter_complex "[0:v]scale=640:-1[a];[1:v]scale=640:-1[b];\
[2:v]scale=640:-1[c];[3:v]scale=640:-1[d];\
[a][b]hstack[top];[c][d]hstack[bot];[top][bot]vstack" diag.png
```
- 对比图存到项目 media 目录（**保留**，作证据），在响应/文档里 embed。

### 5. 落成可追溯结论
- 观测用**表格**（观测项 × 各视频），一句话总结主问题，再给**排序的假设**（恒定偏置 / 随帧漂 / 摆放错 …）。
- 结论必须能指回证据图。跑实验类任务时，把这轮当作一次 experiment 记进实验文档（配合 `experiment-driven-doc`）。

## 原则
- **看图 > 猜**：有视频就抽帧，不要凭直觉下结论。
- **同步对齐第一**：对比前先用元信息确定帧号/时间戳如何对应，错位对齐会得出错误结论。
- **相对关系 + 系统性**：结论建立在"相对谁、是否一致/漂移"上。
- **临时脚本即弃**：抽帧命令一次性；只保留对比图与结论。

## 组合的其它 skill
- `experiment-driven-doc`：把视频复盘作为一轮实验（假设→抽帧→观测→结论→next）记录。
- `feature-dev-pipeline`：复盘产出的对齐/缺陷结论回填 feature.md 的关键结论区。
