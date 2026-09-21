<#
.SYNOPSIS
    Remove only the user-level Cursor links and hook entries installed by agent-loop.

.DESCRIPTION
    Existing backups are left untouched. Restore them manually after uninstall if needed.
#>

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$cursorHome = "$env:USERPROFILE\.cursor"

function Normalize-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Remove-OwnedJunction([string]$Path, [string]$ExpectedTarget) {
    if (-not (Test-Path $Path)) { return }
    $item = Get-Item $Path
    if ($item.LinkType -ne 'Junction') {
        Write-Host "Kept non-junction: $Path" -ForegroundColor Yellow
        return
    }
    $targets = @($item.Target | ForEach-Object { Normalize-Path $_ })
    if ($targets -notcontains (Normalize-Path $ExpectedTarget)) {
        Write-Host "Kept junction with another target: $Path" -ForegroundColor Yellow
        return
    }
    cmd /c "rmdir `"$Path`"" | Out-Null
    Write-Host "Removed $Path" -ForegroundColor Green
}

$hooksJson = "$cursorHome\hooks.json"
if (Test-Path $hooksJson) {
    $cfg = Get-Content $hooksJson -Raw | ConvertFrom-Json
    $hooks = @{}
    if ($cfg.PSObject.Properties.Name -contains 'hooks') {
        foreach ($event in $cfg.hooks.PSObject.Properties.Name) {
            $kept = @($cfg.hooks.$event | Where-Object {
                $_.command -notlike "*memory-lookup*" -and
                $_.command -notlike "*harness-stop*" -and
                $_.command -notlike "*goal-refresh*"
            })
            if ($kept.Count -gt 0) { $hooks[$event] = $kept }
        }
    }
    @{ version = 1; hooks = $hooks } |
        ConvertTo-Json -Depth 10 |
        Set-Content $hooksJson -Encoding utf8
    Write-Host "Removed agent-loop entries from hooks.json" -ForegroundColor Green
}

$skillsDest = "$cursorHome\skills-cursor"
if (Test-Path $skillsDest) {
    $skillsRoot = Normalize-Path "$repo\.cursor\skills"
    Get-ChildItem $skillsDest -Force |
        Where-Object { $_.LinkType -eq 'Junction' } |
        ForEach-Object {
            $targets = @($_.Target | ForEach-Object { Normalize-Path $_ })
            if (@($targets | Where-Object { $_.StartsWith($skillsRoot) }).Count -gt 0) {
                cmd /c "rmdir `"$($_.FullName)`"" | Out-Null
                Write-Host "Removed skill: $($_.Name)" -ForegroundColor Green
            }
        }
}

Remove-OwnedJunction "$cursorHome\rules" "$repo\rules"
Remove-OwnedJunction "$cursorHome\harness" "$repo\harness"
Remove-OwnedJunction "$cursorHome\hooks" "$repo\.cursor\hooks"

Write-Host "`nBackups were not modified. Restart Cursor to unload the hooks." -ForegroundColor Cyan

