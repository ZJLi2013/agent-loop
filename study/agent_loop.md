


## 背景

当前工作范式： `人 → agent → 一个实验 → 人判断 → agent → 下一个实验`

预期：`Goal → Plan → Execute → Observe → Diagnose → Repair / Re-plan → Verify → Continue → Done`


### Anthropic Ralpha Loop

核心是一个orchestration primitive: `agent 想退出 → harness 判断 completion criteria → 没完成 → 把任务重新喂进去 → 新 iteration 继续`


###  [Karpathy/autoresearch](https://github.com/karpathy/autoresearch)


把 agent 工作压缩成一个非常明确的 closed-loop optimization problem。如果 crash 是 typo / missing import 这种简单问题，就自己修；如果 experiment 本身坏了，就记录并跳过，然后继续。**failure 是 input，不是 termination condition**，



## agent_loop 架构

TODO 

