param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Version -notmatch '^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "Version must be semantic, for example 1.2.3 or 1.2.3-rc.1."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$packagedRoot = Join-Path $projectRoot "dist\JobHuntAgent"
$packagedExe = Join-Path $packagedRoot "JobHuntAgent.exe" # dist\JobHuntAgent\JobHuntAgent.exe
$packagedFrontend = Join-Path $packagedRoot "_internal\web_static\index.html"
$installerScript = Join-Path $projectRoot "packaging\installer.iss"
$artifactVerifier = Join-Path $projectRoot "scripts\verify_release_artifact.py"
$installerOutputDir = Join-Path $projectRoot "dist\installer"
$installerOutput = Join-Path $projectRoot "dist\installer\JobHuntAgent-Setup-$Version.exe"

foreach ($requiredPath in @($packagedExe, $packagedFrontend, $installerScript, $artifactVerifier)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required build input is missing: $requiredPath"
    }
}

$pythonCommand = Get-Command "python" -ErrorAction Stop
& $pythonCommand.Source -X utf8 $artifactVerifier $packagedRoot
if ($LASTEXITCODE -ne 0) {
    throw "Release artifact verification failed. Installer compilation was stopped."
}

$compilerCandidates = @()
if ($env:ISCC_PATH) {
    $compilerCandidates += $env:ISCC_PATH
}
if ($env:LOCALAPPDATA) {
    $compilerCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
}
if (${env:ProgramFiles(x86)}) {
    $compilerCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
}
if ($env:ProgramFiles) {
    $compilerCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
}

$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        $compiler = $command.Source
    }
}
if (-not $compiler) {
    throw "Inno Setup 6 compiler (ISCC.exe) was not found. Set ISCC_PATH or install Inno Setup 6."
}

New-Item -ItemType Directory -Path $installerOutputDir -Force | Out-Null

& $compiler "/DMyAppVersion=$Version" $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compiler failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path -LiteralPath $installerOutput)) {
    throw "Installer was not created at the expected path: $installerOutput"
}

Write-Output $installerOutput
