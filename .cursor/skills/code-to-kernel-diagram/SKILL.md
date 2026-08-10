---
name: code-to-kernel-diagram
description: >-
  从神经网络模块源码生成 kernel engineer 视角的数据流图：节点名用源码里的模块名
  （q_proj、q_a_layernorm，不是 gemm / ln），shape 用符号化维度
  （[bs, ql, num_heads, head_dim]，不是 [1, 1, 83, 83]），带权重的节点标 W[in, out]。
  以 forward() 的执行顺序为唯一真相，把 attention / MLP / norm 展开到能对应单个
  GPU kernel 的粒度，并标注 all-reduce 次数、有无 KV cache、可融合的 elementwise。
  Use when asked to draw a component diagram, block diagram, dataflow diagram, or
  a "过哪些 kernel / 从前到后经过什么" flow for a transformer block, DiT block,
  attention module, model layer, or any nn.Module forward path; also when
  explaining an unfamiliar model architecture from its source file. This skill
  owns kernel-granularity dataflow of a single module; it is not for system-level
  architecture diagrams of services, databases, and queues.
---

# Code → Kernel Diagram

把一个 `nn.Module`（transformer block / DiT block / attention / VAE 阶段）的源码，
变成 kernel engineer 能直接对着做性能分析的**文本数据流图 + 与基线的差异**。

读者是 kernel engineer，不是模型使用者。他只关心三件事：**这一步是哪个 kernel、
吃多大的 tensor、权重多大**。不承载这三件事的行都是噪声。

粒度基准：**图上每个节点要能对应到 profiler trace 里的一段**。纯 view（`unflatten`、
`split`、`slice`）不单独成节点，但要挂在产生它的 kernel 下面，
否则读者会以为 shape 是凭空变的。

**"哪些算子不落 kernel"在图外交代一次，不要逐行标 `free`。** 同一个标注出现十几次
就不再是信息而是背景色，写成一行约定放在符号表旁边即可：`split / unflatten / flatten /
transpose / slice 只改 shape；cat 和 expand 后的 reshape 是真拷贝`。
反过来更要小心：`cat`、`einsum`、`sinusoidal_embedding_1d` 都实打实起 kernel，
把它们标成 `free` 比不标危害更大 —— 读者会照着图去掉本该优化的那一段。

---

## Workflow

### 1. 先拿文件骨架，别直接读

用户给的行号常常指向顶层 `XXXModel`，但要画的流程在 `XXXBlock.forward()` 里。
一条命令拿到全部类和 forward 的位置，再决定读哪几段：

```bash
rg -n '^class |def forward' path/to/model.py
```

然后按 `Block.forward` → 它调用的子模块（attention / MLP）→ 子模块的 `__init__`
这个顺序读，通常 3 次读文件够了。

### 2. `forward()` 是执行顺序的唯一真相

**不要按 `__init__` 里的声明顺序画图。** 声明顺序常常和执行顺序不一致
（例如 `img_mod` 声明在最前，但 `txt_mod` 的输入依赖 `forward` 里对 `temb` 的裁剪）。

`__init__` 只用来回答"这个 `self.xxx` 到底是什么算子"：linear 的并行类型
（Column / Row / QKVParallel）、norm 是 LayerNorm 还是 RMSNorm、激活函数是哪个、
attention 是否 causal。

### 3. 复合子模块必须展开，不留黑盒

`self.attn(...)` 不能画成一个写着 "Attention" 的方块。展开成实际序列，
节点名取源码属性名，典型的是（Qwen-Image joint attention）：

```
to_qkv / add_kv_proj → split+view → norm_q / norm_k → rope → cat
→ attn(FMHA) → flatten+slice → to_out / to_add_out
```

MLP 同理展开成 `up GEMM → 激活 → down GEMM + all-reduce`。
展开深度的判据：**再往下拆不会改变 kernel 数量了，就停。**

### 4. 节点名用源码属性名，shape 用符号化维度

全篇最容易做错、也最影响可读性的一条。

**节点名 = 源码里的 `self.xxx`。** 写 `to_qkv`、`img_norm1`、`img_mlp.net.0`，
不写 `QKV Proj`、`LayerNorm`、`MLP Up Proj`。类型名读者自己看得出来，
源码名才是他 grep 回去改代码的唯一入口。带权重的节点后面跟 `W[in, out]`。

**shape 用维度符号，数值只在图顶部的符号表里绑定一次。**
`[1, 6889, 3072]` 的三个数字读者要反查才知道谁是谁；`[bs, s_img, dim]` 自解释，
还能一眼看出 `3·dim`、`H · hd = dim` 这类关系。符号表顺手把推导写上：

```text
 bs      = 1                    batch
 s_img   = 6889 = 83 × 83       image token
 s_joint = 6985 = s_txt + s_img joint 序列
 dim     = 3072 = H · hd        hidden
 H       = 24                   num_heads
 hd      = 128                  head_dim
```

同一段 QKV 的对照：

```text
✗   Img QKV Proj    to_qkv    fused GEMM 3072×9216
        [1,6889,3072] → [1,6889,9216] → split 3×3072 → q,k,v [1,6889,24,128]

✓   to_qkv    W[dim, 3·dim]
        [bs, s_img, dim] → [bs, s_img, 3·dim]
        split 3× + view → q, k, v  [bs, s_img, H, hd]
```

两流同构的位置（QK-Norm、RoPE）用通称 `s` 表示"`s_img` 或 `s_txt`"，
别为了区分两流把同一个 kernel 写两遍。

### 5. 布局：纵向执行顺序 + 横向并行流

用文本图，不用 Mermaid —— 每个节点要挂 2–3 行（名字 + 权重、in shape、out shape），
Mermaid 的方块装不下这些还保持可读。

- 纵向 = 时间顺序；横向 = 并行的数据流（image 流在左、text 流在右）。
- 复合模块（attention）用**左单边框** `┌─ JOINT ATTENTION ─` 圈起来，
  不要用 `╔═══╗` 全包围：语义名比类型名长，右边界一改就错位，维护不起。
- 调制参数、freqs、mask 是**注入**不是主流。用 `◄ scale₁, shift₁` 挂在流线旁边，
  不要拉成和主流平级的箭头，会把图变成蛛网。

图自带源码名和 shape 之后**不要再补一张 kernel 序列表**，那是同一份信息抄两遍。

### 6. 收尾写"与基线的差异"，不要逐个组件讲解

读者已经懂标准 transformer。价值全在**差在哪**，所以最后一节是 3–5 条差异，
每条一句话点题 + 一句话说为什么这么设计或对性能的影响。基线取最近的那个：

| 被画的东西 | 基线 |
|---|---|
| DiT / diffusion block | LLM decoder block |
| 新 attention 变体 | 标准 MHA |
| 双流 / MMDiT | 单流 transformer |

**逐个组件写教科书式解释是这个 skill 最容易跑偏的地方。** "什么是 LayerNorm"
不写；"这里的 LayerNorm 关了 affine，因为 scale/shift 由 timestep 现算"要写。

---

## 每次都要标出的性能锚点

这几条是把图从"结构说明"变成"优化入口"的部分，源码里都能直接数出来：

- **all-reduce 次数** = TP 下 `RowParallelLinear` 的个数（attention out proj + 各 MLP 的 down proj）。
- **有无 KV cache / causal**。`causal=False` 意味着没有被 mask 掉的浪费，
  也意味着不能增量复用、每步全量重算。
- **紧挨着的 elementwise** —— norm 后面跟着 scale/shift、residual 前的 gate 乘法，
  都是 fusion 候选，指出来。
- **已经融合的 GEMM** —— `QKVParallelLinear` 一个 GEMM 出 Q/K/V，别画成三个。
- **只在特定 dtype/条件触发的算子** —— fp16 的 `clip`、dtype cast。画成单独一格并标注条件。

---

## 陷阱

**类名会撒谎，以 `forward` 里实际的 tensor 用法为准。**
真实例子：`QwenImageCrossAttention` 其实是 joint self-attention，不是 cross-attention；
里面的 `add_kv_proj` 出的是 text 的**完整 QKV**，不只是 KV。看到名字和用法不一致，
在正文里明确指出来 —— 这正是读者会踩的坑。

**返回值顺序要注明。** `return encoder_hidden_states, hidden_states` 这种 text 在前的
顺序，接的时候极容易反。

**`nn.Identity()` 占位符不画**（通常是为权重加载对齐 index 留的空位）。

**分支要么画要么说，不要默认走一条。** SP / TP 开启时走的是不同的 attention 调用路径，
选主路径画图，另一条在正文一句话交代。

---

## 自检

- 每个节点名能不能直接 grep 到源码？出现 `GEMM` / `LN` / `Proj` 这类类型名就是没做到。
- shape 里还有裸数字吗？符号表以外的数值都要换成符号。
- 带权重的节点有没有 `W[in, out]`？
- 图里还有逐行的 `free` 吗？view 类算子的约定只该在图外出现一次。
  被标成 `free` 的东西里有没有真起 kernel 的（`cat`、`einsum`、`reshape`）？
- 图上每个节点，能不能在 profiler trace 里找到对应？不能就是画得太抽象或太细。
- 最后一节有没有出现"什么是 X"式的解释？有就删掉。
- all-reduce 次数、causal 与否，有没有写？

完整的输出样例（Qwen-Image 双流 MMDiT block）见 [example.md](example.md)。
