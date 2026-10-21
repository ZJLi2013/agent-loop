<#
.SYNOPSIS
Hands one open auto-fix issue to Codex and opens a pull request for its fix.

.DESCRIPTION
Codex runs in its workspace-write sandbox in a fresh worktree of origin/main and follows agent.md. This script pushes
the regression test alone and requires CI to fail, then pushes the fix and requires CI to pass. It then reverts the
test, so only the fix is merged, and marks the pull request ready once CI passes again. A stop keeps the worktree and
the draft pull request for inspection.

Extra Codex arguments, such as a profile, come from $env:AUTO_FIX_CODEX_ARGS.
#>
param([int]$Issue)

[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$repo = 'ZJLi2013/agent-loop'
$root = (git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
# The worktree's copy is editable by Codex; only the invoking checkout's checker may run here.
$checker = Join-Path $root 'skills\self-report\check_report.py'

function Invoke-Checked {
    $exe, $rest = $args
    & $exe @rest
    if ($LASTEXITCODE) { throw "$exe $rest exited $LASTEXITCODE" }
}

function Stop-Run([string]$Reason) {
    Write-Host "auto-fix stopped: $Reason"
    exit 1
}

function Test-Checks([string]$Pr, [string]$Sha) {
    # gh pr checks reports nothing until GitHub registers the runs for a new head.
    do {
        Start-Sleep 15
        $count = Invoke-Checked gh api "repos/$repo/commits/$Sha/check-runs" -q '.total_count'
    } until ([int]$count -gt 0)
    & gh pr checks $Pr --watch --interval 15 | Out-Host
    return $LASTEXITCODE -eq 0
}

function Get-FailedChecks([string]$Pr) {
    $checks = (& gh pr checks $Pr --json 'name,bucket') -join '' | ConvertFrom-Json
    $(foreach ($c in $checks) { if ($c.bucket -eq 'fail') { $c.name } }) -join ', '
}

if (-not $Issue) {
    $open = Invoke-Checked gh issue list --repo $repo --label auto-fix --state open --json number -q '.[].number'
    $Issue = $open | Sort-Object { [int]$_ } | Where-Object {
        -not (Invoke-Checked gh pr list --repo $repo --state open --label auto-fix --search "#$_ in:body" --json number -q '.[].number')
    } | Select-Object -First 1
    if (-not $Issue) {
        Write-Host 'auto-fix: no open auto-fix issue without an open pull request'
        exit 0
    }
}

$branch = "auto-fix/$Issue"
$wt = Join-Path (Split-Path $root -Parent) "agent-loop-autofix-$Issue"
if (Test-Path $wt) { Stop-Run "$wt already exists" }
Invoke-Checked git -C $root fetch -q origin main
Invoke-Checked git -C $root worktree add -q -b $branch $wt origin/main
$out = Join-Path $wt '.auto-fix'
New-Item -ItemType Directory $out | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)

$data = (Invoke-Checked gh issue view $Issue --repo $repo --json 'title,body,comments') -join "`n" | ConvertFrom-Json
$comments = if ($data.comments) { ($data.comments | ForEach-Object { $_.body }) -join "`n`n---`n`n" } else { '(none)' }
$prompt = (Get-Content (Join-Path $wt '.github\auto-fix\agent.md') -Raw -Encoding UTF8).TrimEnd() +
    "`n`n## Issue #${Issue}: $($data.title)`n`n$($data.body)`n`n### Comments`n`n$comments`n"
[IO.File]::WriteAllText((Join-Path $out 'prompt.md'), ($prompt -replace "`r", ''), $utf8)

$wslWt = (Invoke-Checked wsl -e wslpath -a $wt).Trim()
Invoke-Checked wsl -e bash -lc "cd '$wslWt' && codex exec --skip-git-repo-check -s workspace-write $env:AUTO_FIX_CODEX_ARGS - < .auto-fix/prompt.md"

$stop = Join-Path $out 'stop.md'
if (Test-Path $stop) {
    [IO.File]::AppendAllText($stop, "`n`nAI use: written by Codex through the maintainer's local auto-fix command; not reviewed by a human before posting.`n", $utf8)
    Invoke-Checked python $checker --title "Auto-fix stopped on #$Issue" $stop
    Invoke-Checked gh issue comment $Issue --repo $repo --body-file $stop
    Stop-Run "Codex declined the issue; see $stop"
}
$titleFile = Join-Path $out 'title.txt'
$body = Join-Path $out 'body.md'
if (-not ((Test-Path $titleFile) -and (Test-Path $body))) { Stop-Run 'Codex wrote neither stop.md nor title.txt and body.md' }
if (Invoke-Checked git -C $wt status --porcelain -- .github AI_POLICY.md) { Stop-Run 'Codex changed .github/ or AI_POLICY.md' }
if (-not (Invoke-Checked git -C $wt status --porcelain -- tests)) { Stop-Run 'Codex changed nothing under tests/' }
$title = (Get-Content $titleFile -Encoding UTF8 | Select-Object -First 1).Trim()
Invoke-Checked python $checker --title $title $body

Invoke-Checked git -C $wt add -- tests
Invoke-Checked git -C $wt commit -q -m "Add a regression test for #$Issue"
Invoke-Checked git -C $wt push -q -u origin $branch
$testSha = (Invoke-Checked git -C $wt rev-parse HEAD).Trim()
$pr = (Invoke-Checked gh pr create --repo $repo --draft --base main --head $branch --label auto-fix --title $title --body-file $body | Select-Object -Last 1).Trim()
if (Test-Checks $pr $testSha) {
    Invoke-Checked gh pr comment $pr --body "The regression test passed on the unfixed code, so it does not reproduce #$Issue."
    Stop-Run "CI passed on the test-only commit; see $pr"
}

if (-not (Invoke-Checked git -C $wt status --porcelain -- . ':(exclude).auto-fix')) { Stop-Run "Codex changed nothing outside tests/; see $pr" }
Invoke-Checked git -C $wt add -A -- . ':(exclude).auto-fix'
Invoke-Checked git -C $wt commit -q -m $title
Invoke-Checked git -C $wt push -q
if (-not (Test-Checks $pr (Invoke-Checked git -C $wt rev-parse HEAD).Trim())) {
    $failed = Get-FailedChecks $pr
    Invoke-Checked gh pr comment $pr --body "CI fails with the fix applied: $failed."
    Stop-Run "CI failed with the fix ($failed); see $pr"
}

# The regression test is evidence for this pull request only; keeping every one would grow the suite.
Invoke-Checked git -C $wt revert --no-commit $testSha
Invoke-Checked git -C $wt commit -q -m "Drop the #$Issue regression test after CI confirmed the fix"
Invoke-Checked git -C $wt push -q
if (-not (Test-Checks $pr (Invoke-Checked git -C $wt rev-parse HEAD).Trim())) {
    $failed = Get-FailedChecks $pr
    Invoke-Checked gh pr comment $pr --body "CI fails once the regression test is dropped: $failed."
    Stop-Run "CI failed without the regression test ($failed); see $pr"
}
Invoke-Checked gh pr ready $pr
Write-Host "auto-fix: $pr is ready for review"
