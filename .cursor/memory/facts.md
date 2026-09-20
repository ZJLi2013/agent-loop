# Facts

## install
- `~/.cursor/rules` → 整目录 junction 指向 `.cursor/rules`
- `~/.cursor/hooks` → 整目录 junction 指向 `.cursor/hooks`；`~/.cursor/hooks.json` 由 sync 脚本生成
- `~/.cursor/skills-cursor/<name>` → 逐个 skill 的 junction，共 10 个
- 同步命令：`powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1`（幂等）
- 替换前的 rules 副本备份在 `~/.cursor/rules-backup-20260920`

## env
- Python 3.13.14，`python` 与 `python3` 都可用
- shell 是 PowerShell 5.1（坑见 lessons.md#windows）
