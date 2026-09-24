# Pager Design

## Goal

休假不带电脑时，工位 agent 把心跳和待批事项发到手机，人用短回复让它继续或停下。

## Architecture

```text
工位 agent
    → pager send（唯一 task_id）
    → Microsoft Graph
    → 手机 Outlook
    → 用户回复同一线程
    → pager serve 持续轮询
    → agent 解释结构化指令并执行
```

Pager 通过 `PAGER_GRAPH_SCRIPTS` 注入本机已登录的 Graph 客户端，不保存 token。邮件主题携带
task id；回复必须来自控制邮箱，并与原邮件共享 `conversationId`。

## Command protocol

- `DO <任务>`：自然语言任务，不得直接拼接为 shell 命令。
- `OK`：只批准当前邮件明确写出的动作。
- `NO`：拒绝当前动作。
- `STOP`：在下一个安全检查点停止。

`OK`、`NO`、`STOP` 必须单独占首个非空行。指令从 Graph
`bodyPreview` 读取，避开 Outlook HTML 中的分类标签和引用历史。

一条有效回复会关闭对应 task id。下一轮必须使用新的 task id 和邮件线程。

## State and delivery

本地 JSON 只保存 pending task、conversation id 和已消费 message id，不保存
token 或邮件正文。文件通过同目录临时文件和 `os.replace` 原子提交。状态损坏时
停止运行，不以空状态继续。

`wait` 返回 0 表示收到指令；返回 2 只表示本轮超时，调用方可继续等待。已消费
回复跨进程不会重放。

`serve` 在空轮询后继续运行；Graph 错误按上限退避。它按配置间隔发送普通
heartbeat 通知，通知不创建 pending task。收到 command 后 `serve` 输出 JSON 并退出，
由当前 agent 处理后重新启动。

## Boundaries

- 工作电脑、网络、Graph 登录和现有 agent 会话必须保持可用。
- Pager 不启动、唤醒或恢复 agent；`serve` 也不是系统服务。
- 邮件在 agent 执行前已被消费；agent 随后崩溃可能丢失该任务。
- `STOP` 不能中断已经运行的长命令。
- 手机只承担短指令和审批，不用于调试。
- 不可逆操作仍需单独的人类确认。
