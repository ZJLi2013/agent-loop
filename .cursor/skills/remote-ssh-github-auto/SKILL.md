---
name: remote-ssh-github-auto
version: 1.0.0
author: ZJLi2013
description: 通用远端 SSH 与 GitHub 认证修复流程。先稳定本机到远端的 SSH 登录；再按需使用 SSH Agent Forwarding 或远端独立 key 修复 GitHub 拉取。
disable-model-invocation: true
allowed-tools: [Shell]
---

# 远端 SSH + GitHub 认证修复

## 适用场景

- Agent 需要从本机连接远端 Linux / GPU 节点执行非交互命令。
- 远端 `git pull` 需要 GitHub SSH 认证。
- Windows OpenSSH 在 Conductor GPU 节点 publickey 阶段卡住。

## 连接策略

### 1. 普通 Linux 节点

优先使用 OpenSSH，并显式指定 user/key：

```powershell
ssh -o BatchMode=yes -o ForwardAgent=no `
  -i "C:\Users\<you>\ssh_keys\id_ed25519_new" `
  <user>@<host> "hostname; whoami"
```

验证要求：10 秒内返回。超过 10 秒视为不可用，不继续等待。

### 2. Windows Agent + Conductor GPU 节点

如果 OpenSSH 在 publickey/auth 阶段卡住，改用本 skill 附带的 Paramiko runner。不要使用
ControlMaster / ControlPath / socket 预热方案。

```powershell
python "c:\Users\zhengjli\Documents\github\ai_agents\my_skills\.cursor\skills\remote-ssh-github-auto\scripts\ssh_paramiko.py" `
  --host <host> `
  --user <user> `
  --key "C:\Users\<you>\ssh_keys\id_ed25519_new" `
  --timeout 10 `
  --cmd "hostname; whoami"
```

验证要求：10 秒内返回 exit code 和 stdout。后续 agent 侧远端短命令都使用该 runner。

如果 Conductor publickey 偶发 `Authentication timeout`，不要切回 OpenSSH；直接让
Paramiko runner 自动重试，或显式增加重试次数：

```powershell
python "c:\Users\zhengjli\Documents\github\ai_agents\my_skills\.cursor\skills\remote-ssh-github-auto\scripts\ssh_paramiko.py" `
  --host <host> `
  --user <user> `
  --key "C:\Users\<you>\ssh_keys\id_ed25519_new" `
  --timeout 15 `
  --retries 2 `
  --cmd "docker ps"
```

## 长任务规则

不要让 SSH 连接承载长任务日志。远端长任务必须 detach：

```bash
docker run -d --name <job_name> ... <image> bash -lc '<command>'
```

然后用短命令轮询：

```bash
docker ps -a --filter name=<job_name>
docker logs --tail 80 <job_name>
docker inspect -f '{{.State.ExitCode}}' <job_name>
```

输出、视频、summary 必须写到 host-mounted output 目录，便于任务结束后回传。

## GitHub 认证

Agent forwarding 只用于远端访问 GitHub，不用于修复节点登录。

```powershell
ssh-add C:\Users\<you>\ssh_keys\id_ed25519
ssh -A <user>@<host>
```

远端验证：

```bash
ssh-add -l
ssh -T git@github.com
```

通过后再执行：

```bash
cd <repo_dir>
git remote set-url origin git@github.com:<owner>/<repo>.git
git pull --ff-only
```
