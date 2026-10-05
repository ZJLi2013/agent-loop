# Feishu WebSocket 使用指南

Feishu transport 使用企业自建应用和官方 SDK 的 WebSocket 长连接。工作电脑只需能访问公网，
不需要部署公网 callback URL。

## 1. 准备应用

1. 在飞书开放平台创建企业自建应用。
2. 启用机器人能力并授予发送消息权限。
3. 发布并安装应用。
4. 创建专用群并加入机器人；从开放平台 API 调试台取得：
   - 群的 `chat_id`；
   - 控制者的 `open_id`。

只有 chat ID 与 sender open ID 同时匹配本机 allowlist 的消息才会被接受。凭据和 ID 不要提交
到仓库。

## 2. 安装与配置

Windows Store Python 的 user site 路径较长，安装 `lark-oapi` 时可能超过 Windows 路径上限。
使用短路径虚拟环境可避开：

```powershell
python -m venv C:\venvs\pager
C:\venvs\pager\Scripts\python -m pip install -e "tools/pager[feishu]"

$env:PAGER_TRANSPORT = "feishu"
$env:PAGER_FEISHU_APP_ID = "<app id>"
$env:PAGER_FEISHU_APP_SECRET = "<app secret>"
$env:PAGER_FEISHU_CHAT_ID = "<chat_id>"
$env:PAGER_FEISHU_ALLOWED_SENDER_IDS = "<open_id>"
$env:PAGER_STATE_PATH = "$HOME\.pager\my-project-feishu.json"
```

多个 sender ID 用逗号分隔。环境变量应设在启动 agent 的同一环境中，确保 pager 子进程能够继承。

## 3. 启用长连接

先启动 listener：

```powershell
C:\venvs\pager\Scripts\python -m pager serve --heartbeat-seconds 0
```

保持连接期间：

1. 打开应用的事件订阅配置。
2. 选择长连接作为事件接收方式。
3. 订阅 `im.message.receive_v1`。
4. 保存并发布新的应用版本。

开放平台显示长连接正常后，用 `Ctrl+C` 停止临时 listener。

## 4. 运行 smoke test

发送一个 pending page：

```powershell
C:\venvs\pager\Scripts\python -m pager send `
  --task-id smoke-1 `
  --title "飞书 pager smoke" `
  --body "回复 OK，或直接输入一条自然语言指令"
```

启动 listener：

```powershell
C:\venvs\pager\Scripts\python -m pager serve --heartbeat-seconds 0
```

在专用群回复 `OK`，listener 应退出并输出：

```json
{"status":"command","commands":[{"verb":"OK","task_id":"smoke-1","text":""}]}
```

每个 state file 只允许一个 pending task。显式 `OK`、`NO`、`STOP`、`DO <文字>` 保持原义；
其它非空飞书消息自动成为自然语言 `DO`。

## 5. 接入 agent-loop

smoke 通过后，在目标项目创建 `.agent-loop/pager.json`：

```json
{
  "argv": ["C:\\venvs\\pager\\Scripts\\python.exe", "-m", "pager"],
  "project": "my-project",
  "address": "<chat_id>"
}
```

之后 `agent-loop-harness page` 会通过飞书发送 human checkpoint。电脑、网络、agent 会话和
飞书凭据必须保持可用；pager 不能唤醒或恢复已经退出的 agent。

官方长连接配置见
<https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/event-subscription-guide/long-connection-mode>.
