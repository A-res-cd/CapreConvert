# CapreConvert source launcher. The localraw module is retained for compatibility.
param(
    [switch]$Lan,
    [int]$Port = 8765,
    [string]$Workspace,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) {
    throw 'Project environment missing. Follow README.md setup commands first.'
}
$launchArguments = @('-m', 'localraw', '--port', [string]$Port)
if ($Lan) { $launchArguments += '--lan' }
if ($Workspace) { $launchArguments += @('--workspace', $Workspace) }
if ($NoBrowser) { $launchArguments += '--no-browser' }
Push-Location -LiteralPath $projectRoot
try {
    & $runtime @launchArguments
    $resultCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $resultCode
