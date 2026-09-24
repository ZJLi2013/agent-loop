# pager

Pager 是工作电脑和手机之间的“值班机”：

1. 工作电脑上的 agent 用 Outlook 发来进展或审批请求。
2. 人在手机 Outlook 回复 `OK`、`NO`、`STOP` 或 `DO ...`。
3. agent 读取回复，继续执行或停在安全检查点。

## 需要部署吗？

**不需要部署服务器或常驻 Web 服务。** Pager 是安装在工作电脑上的本地
Python 命令行工具，只会主动访问 Microsoft Graph。

首次使用需要做两件事：

1. 在 agent-loop 根目录安装本地包：

   ```powershell
   python -m pip install -e tools/pager
   ```

2. 准备一个已登录的 Microsoft Graph 客户端：一个目录里的 `graph_client.py`，提供
   `GraphClient().get(path, params)` 与 `.post(path, body)`，并让 pager 找到它：

   ```powershell
   setx PAGER_GRAPH_SCRIPTS "C:\path\to\graph-client-scripts"
   ```

Pager 不保存 token，登录由这个客户端负责。休假期间还需满足：

- 工作电脑保持开机、不休眠，并能访问邮箱所在网络；
- Graph 登录仍有效；
- 现有 agent 会话保持运行，并启动 `pager serve`。

Pager 不能唤醒已经退出的 agent，也不能在 agent 崩溃后重新执行已消费的任务。

## 一个通俗示范

假设 agent 正在整理报告，需要你决定是否继续生成全文。

### 1. Agent 发邮件到你的手机

工作电脑执行：

```powershell
$env:PAGER_CONTROL_ADDRESS = "your.name@example.com"
$env:PAGER_STATE_PATH = "$HOME\.pager\report.json"

python -m pager send `
  --task-id report-20260923-01 `
  --title "是否继续生成报告？" `
  --body "回复 OK 继续，回复 NO 取消"
```

手机 Outlook 会收到主题类似下面的邮件：

```text
[agent report-20260923-01] 是否继续生成报告？
```

### 2. 你用手机回复

回复正文首行只写：

```text
OK
```

也可以直接下发一个自然语言任务：

```text
DO 先只生成摘要，全文暂缓
```

`OK`、`NO`、`STOP` 必须单独占首个非空行，不能写成
`OK，顺便……`；只有 `DO` 后面可以带文本。

### 3. Agent 持续等待并取得指令

工作电脑执行：

```powershell
python -m pager serve --heartbeat-seconds 3600
```

收到回复时输出：

```json
{"status":"command","commands":[{"verb":"OK","task_id":"report-20260923-01","text":""}]}
```

agent 据此继续生成报告，再用新的 task id 发下一封进展邮件。若输出
command JSON，`serve` 正常结束；agent 处理后重新启动 `serve`。没有回复时
`serve` 不会因 timeout 退出，并且默认每小时发一封 `[pager] listener alive`
心跳邮件。

临时只等一轮仍可使用：

```powershell
python -m pager wait --timeout 300
```

`wait` 超时会输出 `{"status":"timeout"}` 并返回 2；pending 邮件不会丢失。

## 长期等待与心跳

```powershell
python -m pager serve `
  --interval 10 `
  --heartbeat-seconds 3600 `
  --max-errors 3
```

- 空轮询会继续等待。
- Graph 错误按退避重试，连续达到上限后返回错误。
- 心跳是普通通知，不创建可回复的 pending task。
- `--heartbeat-seconds 0` 可关闭邮件心跳。

`serve` 仍是工作电脑上的前台进程。关闭终端、退出 agent 或重启电脑都会停止它；
当前版本没有 Windows 服务、自启动或 agent 唤醒能力。

## 回复含义

- `DO <任务>`：把自然语言任务交给当前 workspace 的 agent，不能直接拼成 shell。
- `OK`：只批准当前邮件写明的动作。
- `NO`：拒绝当前动作。
- `STOP`：在下一个安全检查点停止；不能中断已经运行的长命令。

每封控制邮件只消费一个有效回复。后续指令应回复 agent 新发出的邮件。

## 开发

```powershell
python -m pip install -e "tools/pager[dev]"
python -m pytest tools/pager/tests -q
```

接入 agent-loop 的检查点见仓库根 README「人不在电脑前」。

实现边界见 [design.md](design.md)，agent 操作约定见
[docs/agent-runbook.md](docs/agent-runbook.md)。
