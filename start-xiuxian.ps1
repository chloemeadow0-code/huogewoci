# Qingyun MCP launcher, based on the original deployment entry point.
param(
    [ValidateSet('server', 'http', 'demo', 'test')]
    [string]$Mode = 'server',
    [string]$Database = ''
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '请先按 README.md 创建 .venv 并安装依赖。'
}
if (-not $Database) { $Database = Join-Path $PSScriptRoot 'data\xiuxian.db' }
$previousPythonPath = $env:PYTHONPATH
$previousEncoding = $env:PYTHONIOENCODING
try {
    $env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
    $env:PYTHONIOENCODING = 'utf-8'
    if ($Mode -eq 'server') {
        & $pythonPath -m xiuxian.server --db $Database
    } elseif ($Mode -eq 'http') {
        & $pythonPath -m xiuxian.http_app
    } elseif ($Mode -eq 'demo') {
        & $pythonPath -m xiuxian.demo --output (Join-Path $PSScriptRoot 'xiuxian-demo.json')
    } else {
        & $pythonPath -m pytest (Join-Path $PSScriptRoot 'tests\xiuxian') -q
    }
    if ($LASTEXITCODE -ne 0) { throw "运行失败，退出码 $LASTEXITCODE" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONIOENCODING = $previousEncoding
}
