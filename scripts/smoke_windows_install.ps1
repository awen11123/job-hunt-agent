param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [ValidateRange(10, 180)]
    [int]$StartupTimeoutSeconds = 60,

    [switch]$KeepTemporaryFilesOnFailure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$smokeRoot = Join-Path $temporaryRoot ("JobHuntAgent-Smoke-" + [guid]::NewGuid().ToString("N"))
$installDir = Join-Path $smokeRoot "app"
$profileDir = Join-Path $smokeRoot "profile"
$appDataDir = Join-Path $profileDir "JobHuntAgent"
$instancePath = Join-Path $appDataDir "instance.json"
$sentinelPath = Join-Path $appDataDir "keep-after-uninstall.txt"
$appExe = Join-Path $installDir "JobHuntAgent.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
$appProcess = $null
$installed = $false
$previousAppData = $env:APPDATA
$previousSkipBrowser = $env:JOB_HUNT_AGENT_SKIP_BROWSER
$succeeded = $false

try {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    $setupArguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/DIR=`"$installDir`""
    )
    $setup = Start-Process -FilePath $installerPath -ArgumentList $setupArguments -Wait -PassThru
    if ($setup.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $appExe)) {
        throw "Silent installation failed."
    }
    $installed = $true

    $env:APPDATA = $profileDir
    $env:JOB_HUNT_AGENT_SKIP_BROWSER = "1"
    $appProcess = Start-Process -FilePath $appExe -WindowStyle Hidden -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $healthyUrl = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($appProcess.HasExited) {
            throw "Installed application exited before becoming healthy."
        }
        if (Test-Path -LiteralPath $instancePath) {
            try {
                $state = Get-Content -LiteralPath $instancePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $candidateUrl = "http://127.0.0.1:$($state.port)/api/health"
                $health = Invoke-RestMethod -Uri $candidateUrl -Method Get -TimeoutSec 2
                if ($health.status -eq "ok") {
                    $healthyUrl = $candidateUrl
                    break
                }
            }
            catch {
                # The state file or server may not be ready yet.
            }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $healthyUrl) {
        $instanceState = if (Test-Path -LiteralPath $instancePath) { "present" } else { "missing" }
        throw (
            "Installed application did not become healthy within " +
            "$StartupTimeoutSeconds seconds. InstanceState=$instanceState."
        )
    }

    New-Item -ItemType Directory -Path $appDataDir -Force | Out-Null
    Set-Content -LiteralPath $sentinelPath -Value "preserve" -Encoding ASCII

    Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
    $appProcess.WaitForExit(5000) | Out-Null
    $appProcess = $null

    $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -Wait -PassThru
    if ($uninstallProcess.ExitCode -ne 0) {
        throw "Silent uninstall failed."
    }
    $installed = $false
    if (Test-Path -LiteralPath $appExe) {
        throw "Application executable remained after uninstall."
    }
    if (-not (Test-Path -LiteralPath $sentinelPath)) {
        throw "Uninstall removed user data."
    }

    $succeeded = $true
    Write-Output "Smoke test passed: $healthyUrl"
}
finally {
    if ($appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($installed -and (Test-Path -LiteralPath $uninstaller)) {
        Start-Process -FilePath $uninstaller -ArgumentList @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART"
        ) -Wait | Out-Null
    }
    if ($null -eq $previousAppData) {
        Remove-Item Env:APPDATA -ErrorAction SilentlyContinue
    }
    else {
        $env:APPDATA = $previousAppData
    }
    if ($null -eq $previousSkipBrowser) {
        Remove-Item Env:JOB_HUNT_AGENT_SKIP_BROWSER -ErrorAction SilentlyContinue
    }
    else {
        $env:JOB_HUNT_AGENT_SKIP_BROWSER = $previousSkipBrowser
    }

    $resolvedSmokeRoot = [IO.Path]::GetFullPath($smokeRoot)
    $expectedPrefix = $temporaryRoot + [IO.Path]::DirectorySeparatorChar
    $cleanupAllowed = $succeeded -or -not $KeepTemporaryFilesOnFailure
    if (
        $cleanupAllowed -and
        $resolvedSmokeRoot.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedSmokeRoot).StartsWith("JobHuntAgent-Smoke-")
    ) {
        Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    elseif (-not $cleanupAllowed) {
        Write-Output "Smoke diagnostics retained: $resolvedSmokeRoot"
    }
}
