param(
    [Parameter(Position = 0)]
    [string]$Path = "data",

    [Parameter(Position = 1)]
    [string]$Out = "handoff/answers.json"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Test-Path -LiteralPath $Path) {
    $Path = (Resolve-Path -LiteralPath $Path).Path
}

& python (Join-Path $root "solve.py") "$Path" --out "$Out"
exit $LASTEXITCODE
