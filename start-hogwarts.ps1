# Hogwarts extension launcher, added 2026-10-02; upstream files are unchanged.
param(
    [ValidateSet('server', 'http', 'demo', 'test')]
    [string]$Mode = 'server',
    [string]$Database = ''
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '请先按 HOGWARTS.md 创建 .venv 并安装依赖。'
}
if (-not $Database) { $Database = Join-Path $PSScriptRoot 'data\hogwarts.db' }
$previousPythonPath = $env:PYTHONPATH
$previousEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    $env:PYTHONIOENCODING = 'utf-8'
    if ($Mode -eq 'server') {
        & $pythonPath -m hogwarts.server --db $Database
    } elseif ($Mode -eq 'http') {
        & $pythonPath -m hogwarts.http_app
    } elseif ($Mode -eq 'demo') {
        & $pythonPath -m hogwarts.demo --output (Join-Path $PSScriptRoot 'hogwarts-demo.json')
    } else {
        & $pythonPath -m pytest (Join-Path $PSScriptRoot 'tests\hogwarts') -q
    }
    if ($LASTEXITCODE -ne 0) { throw "运行失败，退出码 $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONIOENCODING = $previousEncoding
}
