[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$scriptPath = Join-Path $PSScriptRoot "build_gui.py"

Push-Location $repoRoot
try {
    & python $scriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "build_gui.py 执行失败，退出码: $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
