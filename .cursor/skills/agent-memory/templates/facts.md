# Facts

<!-- 就地覆盖，只留当前值。一条一行，全文 ~10 行。
     准入：后面每轮都要用 + 重查一次要花条命令。两条都满足才写。 -->

## environment
- 远端：`user@node-a`，storage type A，`/data` 独立挂载
- 容器：`myjob-0918`，image `rocm/pytorch:6.2`

## data
- ckpt：`/data/ckpt/run7/step_4000`
- HF 缓存：`/data/cache/huggingface`

## model
- 分支：`feat/x`，远端仓库 `/data/work/repo`
