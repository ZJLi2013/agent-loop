<#
.SYNOPSIS
    把本库的 rules、skills、Harness 与 hooks 链接到 Cursor 的全局目录。幂等，可反复跑。

.DESCRIPTION
    每次增删或重命名 skill 之后重跑一次——失效的 junction 会被清掉，新增的会补上。
    无需管理员权限。

    rules 用整目录 junction，skills 逐个 junction：全局 skills-cursor/ 里还混着
    Cursor 自带的 skill，不能整目录替换。

    不要改用硬链接（mklink /H）链 rules：硬链接绑的是文件本身，而 git pull /
    git checkout 是「删掉重写」，一拉就断，之后仓库改动再也不会反映到 Cursor，
    且不会有任何报错。
#>

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor" | Out-Null

# --- Rules：整目录 junction ---
$rulesDest = "$env:USERPROFILE\.cursor\rules"
if (Test-Path $rulesDest) {
    if ((Get-Item $rulesDest).LinkType) {
        cmd /c "rmdir `"$rulesDest`"" | Out-Null   # PS 5.1 的 Remove-Item 删 junction 会抛 NullReferenceException
    } else {
        $bk = "$rulesDest-backup-$(Get-Date -f yyyyMMdd-HHmmss)"
        Move-Item $rulesDest $bk          # 保住本地独有、尚未入库的 rule
        Write-Host "Backed up existing rules to $bk" -ForegroundColor Yellow
    }
}
cmd /c "mklink /J `"$rulesDest`" `"$repo\rules`"" | Out-Null
Write-Host "Linked rules/ -> $repo\rules" -ForegroundColor Green

# --- Skills：先清失效链接，再补新增的 ---
$skillsDest = "$env:USERPROFILE\.cursor\skills-cursor"
New-Item -ItemType Directory -Force $skillsDest | Out-Null

Get-ChildItem $skillsDest -Force |
    Where-Object { $_.LinkType -eq 'Junction' -and -not (Test-Path ($_.Target -join '')) } |
    ForEach-Object {
        cmd /c "rmdir `"$($_.FullName)`"" | Out-Null
        Write-Host "Pruned dead link: $($_.Name)" -ForegroundColor Yellow
    }

Get-ChildItem "$repo\skills" -Directory | ForEach-Object {
    $t = Join-Path $skillsDest $_.Name
    if (-not (Test-Path $t)) {
        cmd /c "mklink /J `"$t`" `"$($_.FullName)`"" | Out-Null
        Write-Host "Linked skill: $($_.Name)" -ForegroundColor Green
    }
}

# --- Harness：整目录 junction ---
$harnessSrc  = "$repo\harness"
$harnessDest = "$env:USERPROFILE\.cursor\harness"
if (Test-Path $harnessDest) {
    if ((Get-Item $harnessDest).LinkType) {
        cmd /c "rmdir `"$harnessDest`"" | Out-Null
    } else {
        $bk = "$harnessDest-backup-$(Get-Date -f yyyyMMdd-HHmmss)"
        Move-Item $harnessDest $bk
        Write-Host "Backed up existing harness/ to $bk" -ForegroundColor Yellow
    }
}
cmd /c "mklink /J `"$harnessDest`" `"$harnessSrc`"" | Out-Null
Write-Host "Linked harness/ -> $harnessSrc" -ForegroundColor Green

# --- Hooks：整目录 junction + 合并 hooks.json ---
# hook 必须装到 user 级，否则只在本仓库生效，而 memory 要用在各个工作项目里。
# user hook 的 command 路径相对 ~/.cursor/，所以这里写 ./hooks/...
$hooksSrc  = "$repo\adapters\cursor\hooks"
$hooksDest = "$env:USERPROFILE\.cursor\hooks"
if (Test-Path $hooksSrc) {
    $hooksItem = Get-Item $hooksDest -Force -ErrorAction SilentlyContinue
    if ($null -ne $hooksItem) {
        if ($hooksItem.LinkType) { cmd /c "rmdir `"$hooksDest`"" | Out-Null }
        else {
            $bk = "$hooksDest-backup-$(Get-Date -f yyyyMMdd-HHmmss)"
            Move-Item $hooksDest $bk
            Write-Host "Backed up existing hooks/ to $bk" -ForegroundColor Yellow
        }
    }
    cmd /c "mklink /J `"$hooksDest`" `"$hooksSrc`"" | Out-Null
    Write-Host "Linked hooks/ -> $hooksSrc" -ForegroundColor Green

    $hooksJson = "$env:USERPROFILE\.cursor\hooks.json"
    $ours     = @{ command = "python ./hooks/memory-lookup.py"; matcher = "Read"; timeout = 10 }
    $harnessStop = @{ command = "python ./hooks/harness-stop.py"; timeout = 10; loop_limit = 5 }
    $goalRefresh = @{ command = "python ./hooks/goal-refresh.py"; timeout = 10 }
    if (Test-Path $hooksJson) {
        # 保留别处配置的 hook，只替换我们自己那一条。
        # 不用 ConvertFrom-Json -AsHashtable：该参数是 PS 6+，PS 5.1 上会直接报错。
        $cfg = Get-Content $hooksJson -Raw | ConvertFrom-Json
        $existing = @()
        if ($cfg.PSObject.Properties.Name -contains 'hooks' -and
            $cfg.hooks.PSObject.Properties.Name -contains 'postToolUse') {
            $existing = @($cfg.hooks.postToolUse | Where-Object { $_.command -notlike "*memory-lookup*" })
        }
        $merged = @{ version = 1; hooks = @{ postToolUse = @($existing) + @($ours) } }
        # 其它事件原样保留
        if ($cfg.PSObject.Properties.Name -contains 'hooks') {
            foreach ($evt in $cfg.hooks.PSObject.Properties.Name) {
                if ($evt -ne 'postToolUse') { $merged.hooks[$evt] = $cfg.hooks.$evt }
            }
        }
        $keptStop = @()
        if ($merged.hooks.ContainsKey('stop')) {
            $keptStop = @($merged.hooks['stop'] | Where-Object {
                $_.command -notlike "*stop-probe*" -and $_.command -notlike "*harness-stop*"
            })
        }
        $merged.hooks['stop'] = @($keptStop) + @($harnessStop)
        $keptCompact = @()
        if ($merged.hooks.ContainsKey('preCompact')) {
            $keptCompact = @($merged.hooks['preCompact'] | Where-Object {
                $_.command -notlike "*goal-refresh*"
            })
        }
        $merged.hooks['preCompact'] = @($keptCompact) + @($goalRefresh)
        $merged | ConvertTo-Json -Depth 10 | Set-Content $hooksJson -Encoding utf8
        Write-Host "Merged memory, Harness, and Goal Review hooks into existing hooks.json" -ForegroundColor Green
    } else {
        @{ version = 1; hooks = @{
            postToolUse = @($ours)
            stop = @($harnessStop)
            preCompact = @($goalRefresh)
        } } |
            ConvertTo-Json -Depth 10 | Set-Content $hooksJson -Encoding utf8
        Write-Host "Wrote hooks.json with memory, Harness, and Goal Review hooks" -ForegroundColor Green
    }
}

# --- 私有配置（可选，文件不存在就跳过）---
$cfg = "$repo\.agent-loop\configs\node_inventory.yaml"
if (Test-Path $cfg) {
    New-Item -ItemType Directory -Force "$env:USERPROFILE\.agent-loop\configs" | Out-Null
    $t = "$env:USERPROFILE\.agent-loop\configs\node_inventory.yaml"
    Remove-Item $t -Force -ErrorAction SilentlyContinue
    cmd /c "mklink /H `"$t`" `"$cfg`"" | Out-Null
    Write-Host "Linked node_inventory.yaml" -ForegroundColor Green
}

# --- 验证：看链接类型，不是看文件在不在 ---
Write-Host "`n--- Verify ---" -ForegroundColor Cyan
"rules/ LinkType = $((Get-Item $rulesDest).LinkType)   (必须是 Junction)"
"harness/ LinkType = $((Get-Item $harnessDest).LinkType)   (必须是 Junction)"
Get-ChildItem $skillsDest -Force | Where-Object { $_.LinkType -eq 'Junction' } | ForEach-Object {
    "{0,-26} target-exists={1}" -f $_.Name, (Test-Path ($_.Target -join ''))
}
Write-Host "`nCursor 重启后生效。" -ForegroundColor Cyan
