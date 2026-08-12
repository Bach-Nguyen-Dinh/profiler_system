<#
.SYNOPSIS
    Compiles install.ps1 into dist\ProfilerSetup.exe.

.DESCRIPTION
    Wraps the installer in a real executable using the ps2exe module, which is
    installed from the PowerShell Gallery for the current user if missing.

    The produced .exe still needs analyzer.py beside it: it installs *this*
    repo, so ship it in the repo folder (or alongside a copy of it), exactly
    like Install-Profiler.cmd. install.ps1 already resolves its own location
    from the running image, so it works either way.

    The .exe is unsigned, so Windows SmartScreen shows "Windows protected your
    PC" the first time it is run on another machine -- More info -> Run anyway.
    Sign it with signtool if you plan to distribute it widely.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\build_installer.ps1
#>
[CmdletBinding()]
param(
    # Defaulted in the body, not here: $PSScriptRoot is not reliably populated
    # while param defaults are being evaluated.
    [string]$OutputDir,
    [string]$Version = '1.0.0.0'
)

$ErrorActionPreference = 'Stop'

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputDir) { $OutputDir = Join-Path $repoDir 'dist' }

$source = Join-Path $repoDir 'install.ps1'
if (-not (Test-Path $source)) { throw "install.ps1 not found in $repoDir" }

if (-not (Get-Module -ListAvailable -Name ps2exe)) {
    Write-Host 'Installing the ps2exe module for the current user...'
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    # Install-Module bootstraps the NuGet provider through a confirmation
    # prompt, which throws outright in a non-interactive host. Fetching the
    # provider first turns that into an ordinary download.
    if (-not (Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue)) {
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 `
            -Scope CurrentUser -Force | Out-Null
    }
    # PSGallery is untrusted by default; -Force answers that prompt too.
    Install-Module -Name ps2exe -Scope CurrentUser -Force -AllowClobber
}
Import-Module ps2exe

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
$output = Join-Path $OutputDir 'ProfilerSetup.exe'

Write-Host "Compiling $source -> $output"
Invoke-ps2exe -inputFile $source -outputFile $output `
    -title 'Profiler Setup' `
    -description 'Installs the Windows system profiler and its dependencies' `
    -product 'Profiler System' `
    -version $Version `
    -requireAdmin:$false        # the installer needs no elevation at any point

if (-not (Test-Path $output)) { throw 'ps2exe did not produce an executable.' }

Write-Host ''
Write-Host "Built $output" -ForegroundColor Green
Write-Host 'Copy it into the repo folder (next to analyzer.py) and double-click it.'
