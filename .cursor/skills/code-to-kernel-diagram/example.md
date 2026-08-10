# 输出样例：Qwen-Image 双流 MMDiT block

源码：`vllm_omni/diffusion/models/qwen_image/qwen_image_transformer.py`
（`QwenImageTransformerBlock.forward` + `QwenImageCrossAttention.forward` + `FeedForward`）

以下是这个 skill 的完整输出形态，可直接作为格式模板。

---

这是个**双流 MMDiT block**（SD3 那一支）：image 和 text 各有独立的调制 / norm / MLP 权重，
但 **attention 是联合的** —— 两流 concat 成一条序列算一次。

节点名是源码里的模块名，`W[...]` 是权重形状。图里 `chunk` / `split` / `view` /
`flatten` / `slice` 只改 shape、不落 kernel；`cat` 是真拷贝。
维度符号（数值按 1328×1328 T2I，只在这里绑定一次）：

```text
 bs      = 1                     batch
 s_img   = 6889 = 83 × 83        image token
 s_txt   = 96                    text token
 s_joint = 6985 = s_txt + s_img  joint 序列
 dim     = 3072 = H · hd         hidden
 H       = 24                    num_heads
 hd      = 128                   head_dim
 ffn     = 12288 = 4 · dim
 rope_d  = 64                    RoPE 复数对数
 s       = s_img 或 s_txt        两流同构处的通称
```

## ① 调制参数：每层从 temb 现算

```text
  temb  [bs, dim]                              全层共享的 timestep embedding
         │
         ├──────────────────────┬──────────────────────
         ▼                      ▼
  img_mod.1   W[dim, 6·dim]           txt_mod.1   W[dim, 6·dim]
    SiLU + GEMM, replicated             SiLU + GEMM, replicated
         │  [bs, 6·dim]                      │  [bs, 6·dim]
         ▼                                   ▼
  chunk(2) → chunk(3) → unsqueeze
    mod1, mod2  [bs, 3·dim]
    每份再拆 shift, scale, gate  [bs, 1, dim]

  注入点：mod1 → img_norm1 / gate₁      mod2 → img_norm2 / gate₂
```


## ② 主数据流

`◄` 是 ① 产出的参数注入点。

```text
  IMAGE stream                                 TEXT stream
  [bs, s_img, dim]                             [bs, s_txt, dim]
         │  ◄ scale₁, shift₁                          │  ◄ scale₁, shift₁
         ▼                                            ▼
  img_norm1   AdaLayerNorm                     txt_norm1   AdaLayerNorm
         │  [bs, s_img, dim]                          │  [bs, s_txt, dim]
         └──────────────────────┬─────────────────────┘
                                ▼
  ┌─ JOINT ATTENTION ────────────────────────────────────────────────────────
  │
  │  to_qkv        W[dim, 3·dim]                       image QKV, fused
  │      [bs, s_img, dim] → [bs, s_img, 3·dim]
  │      split 3× + view → q, k, v  [bs, s_img, H, hd]
  │
  │  add_kv_proj   W[dim, 3·dim]                       text QKV, fused
  │      [bs, s_txt, dim] → [bs, s_txt, 3·dim]
  │      split 3× + view → q, k, v  [bs, s_txt, H, hd]
  │                                │
  │                                ▼
  │  norm_q · norm_k · norm_added_q · norm_added_k     RMSNorm over hd
  │      q, k  [bs, s, H, hd] → [bs, s, H, hd]
  │                                │
  │                                ▼
  │  rope          vid_freqs [s_img, rope_d]   txt_freqs [s_txt, rope_d]
  │      q, k  [bs, s, H, hd] → [bs, s, H, hd]
  │                                │
  │                                ▼
  │  cat  dim=1, txt ⊕ img
  │      [bs, s_txt, H, hd] + [bs, s_img, H, hd] → [bs, s_joint, H, hd]
  │                                │
  │                                ▼
  │  attn          FMHA  causal=False  softmax_scale = 1/√hd
  │      q, k, v  [bs, s_joint, H, hd] → [bs, s_joint, H, hd]
  │                                │
  │                                ▼
  │  flatten + slice
  │      [bs, s_joint, H, hd] → [bs, s_joint, dim]
  │      → txt [bs, s_txt, dim]  ·  img [bs, s_img, dim]
  │                                │
  │            ┌───────────────────┴────────────────────┐
  │            ▼                                        ▼
  │  to_out   W[dim, dim] +all-reduce         to_add_out   W[dim, dim] +all-reduce
  │      [bs, s_img, dim] → [bs, s_img, dim]      [bs, s_txt, dim] → [bs, s_txt, dim]
  └──────────────────────────────────────────────────────────────────────────
         │                                            │
         ▼  ◄ gate₁                                   ▼  ◄ gate₁
  gated residual   h += gate₁ · x               gated residual   h += gate₁ · x
         │  [bs, s_img, dim]                          │  [bs, s_txt, dim]
         ▼  ◄ scale₂, shift₂                          ▼  ◄ scale₂, shift₂
  img_norm2   AdaLayerNorm                     txt_norm2   AdaLayerNorm
         │  [bs, s_img, dim]                          │  [bs, s_txt, dim]
         ▼                                            ▼
  img_mlp.net.0   W[dim, ffn]                  txt_mlp.net.0   W[dim, ffn]
         │  [bs, s_img, ffn]                          │  [bs, s_txt, ffn]
         ▼                                            ▼
  GELU   tanh-approx                           GELU   tanh-approx
         │  [bs, s_img, ffn]                          │  [bs, s_txt, ffn]
         ▼                                            ▼
  img_mlp.net.2   W[ffn, dim] +all-reduce      txt_mlp.net.2   W[ffn, dim] +all-reduce
         │  [bs, s_img, dim]                          │  [bs, s_txt, dim]
         ▼  ◄ gate₂                                   ▼  ◄ gate₂
  gated residual   h += gate₂ · x               gated residual   h += gate₂ · x
         │  [bs, s_img, dim]                          │  [bs, s_txt, dim]
         ▼                                            ▼
  [bs, s_img, dim]                             [bs, s_txt, dim]
```

