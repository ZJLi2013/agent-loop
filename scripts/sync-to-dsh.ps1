<#
.SYNOPSIS
    把本库 always-apply 的 rules 与 skills 分发到 dsh 的 harness home。幂等，可反复跑。

.DESCRIPTION
    scripts/install-skills.py 做两件事：把 skill 逐个链接到 $DshHome\skills\<name>，含
    ~/.agent-loop/packs.txt 登记的包 skill，那里其他 skill 不动；dsh 不读 .mdc，选中的
    always-apply rule（本库与包的）去掉 frontmatter 后按文件名顺序拼成 $DshHome\AGENTS.md，
    这是生成文件，rule 改动后重跑。hooks 与 provider 仍按 docs/usage.md 手工配置。
#>
param([string]$DshHome = $env:DSH_HOME)

$ErrorActionPreference = 'Stop'
if (-not $DshHome) { throw "dsh home not set: pass -DshHome <path> or set DSH_HOME (dsh defaults to ~/.dsh)" }
$repo = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force $DshHome | Out-Null

python "$repo\scripts\install-skills.py" --host dsh --home $DshHome
exit $LASTEXITCODE
