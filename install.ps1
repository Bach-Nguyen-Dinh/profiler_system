<#
.SYNOPSIS
    Sets up everything the profiler needs, then installs a `profiler` command.

.DESCRIPTION
    Run this once. It:

      1. finds a Python interpreter,
      2. pip installs every package in requirements.txt,
      3. writes a `profiler` shim to %LOCALAPPDATA%\Programs\profiler and puts
         that folder on the user PATH,
      4. verifies the result with `analyzer.py diagnose`.

    Nothing here needs Administrator rights, and nothing is left running in the
    background. Every metric the profiler samples -- CPU, memory, per-core
    frequency, package power and temperature -- comes from Windows performance
    counters read directly through ctypes, so there is no monitoring service to
    install, no kernel driver, and no logon task.

    The shim hard-codes both the interpreter and the repo path found at install
    time -- re-run this script if you move the repo or switch virtualenv.

.EXAMPLE
    .\Install-Profiler.cmd

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir D:\tools\profiler
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\profiler"
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------- script path
# $PSScriptRoot is empty when this script has been compiled into an .exe by
# build_installer.ps1, so fall back to the running image's own path.
$scriptPath = $MyInvocation.MyCommand.Path
if (-not $scriptPath) {
    $scriptPath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
}
$repoDir = Split-Path -Parent $scriptPath

function Write-Step { param([string]$Text) Write-Host "`n==> $Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text) Write-Host "    $Text" -ForegroundColor Green }
function Write-Info { param([string]$Text) Write-Host "    $Text" }

Write-Host "Profiler setup" -ForegroundColor White
Write-Host "==============" -ForegroundColor White
Write-Info "Repo: $repoDir"

$analyzer = Join-Path $repoDir 'analyzer.py'
if (-not (Test-Path $analyzer)) {
    throw ("analyzer.py not found next to the installer (looked in $repoDir). " +
           "Keep the installer in the profiler repo folder and re-run it.")
}

# --------------------------------------------------------------- interpreter
Write-Step 'Looking for Python'
$python = $null
foreach ($candidate in @('python', 'py')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    # Resolve the real interpreter, so the shim cannot end up pointing at the
    # Microsoft Store python.exe alias stub that ships enabled on Windows 11.
    try { $resolved = & $cmd.Source -c "import sys; print(sys.executable)" 2>$null } catch { continue }
    if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved)) {
        $python = $resolved.Trim()
        break
    }
}
if (-not $python) {
    throw ("No working Python interpreter found on PATH. " +
           "Install Python 3.8+ from https://www.python.org/downloads/ " +
           "(tick 'Add python.exe to PATH') and run this installer again.")
}
$pyVersion = (& $python -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
Write-Ok "Python $pyVersion at $python"

# -------------------------------------------------------------- dependencies
Write-Step 'Installing Python dependencies'
$requirements = Join-Path $repoDir 'requirements.txt'
if (-not (Test-Path $requirements)) { throw "requirements.txt not found in $repoDir" }

& $python -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Info 'pip is missing; bootstrapping it with ensurepip...'
    & $python -m ensurepip --default-pip
}

& $python -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) {
    # A system-wide interpreter (Program Files, or the one shipped by an IDE)
    # is not writable by a standard user; --user targets the profile instead.
    Write-Info 'Retrying the install into your user site-packages...'
    & $python -m pip install --disable-pip-version-check --user -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'pip could not install the dependencies.' }
}

$verify = @'
import importlib.util, sys
missing = [p for p in ["psutil", "pandas", "matplotlib", "numpy"]
           if importlib.util.find_spec(p) is None]
if missing:
    print("still missing: " + " ".join(missing))
    sys.exit(1)
'@
$verify | & $python -
if ($LASTEXITCODE -ne 0) { throw 'Some required packages are still not importable.' }
Write-Ok 'psutil, pandas, matplotlib, numpy installed'

# ----------------------------------------------------------------- shim, PATH
Write-Step 'Installing the `profiler` command'
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
$shim = Join-Path $InstallDir 'profiler.cmd'
@"
@echo off
"$python" "$analyzer" %*
"@ | Out-File -FilePath $shim -Encoding ascii -Force
Write-Ok "Wrote $shim"

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -split ';' -notcontains $InstallDir) {
    $newPath = if ([string]::IsNullOrEmpty($userPath)) { $InstallDir } else { "$userPath;$InstallDir" }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Ok "Added $InstallDir to your user PATH."
    Write-Info 'Open a new terminal for the `profiler` command to be found.'
} else {
    Write-Ok "$InstallDir is already on your user PATH."
}

# ---------------------------------------------------------------- final check
Write-Step 'Checking what this machine can measure'
& $python $analyzer diagnose
$diagnoseCode = $LASTEXITCODE

Write-Host ''
if ($diagnoseCode -eq 0) {
    Write-Host 'Setup complete.' -ForegroundColor Green
    Write-Host ''
    Write-Host 'In a NEW terminal:'
    Write-Host '  profiler <target_script.py> [options] -- [target script args]'
    Write-Host '  profiler diagnose'
} else {
    Write-Host 'Setup finished, but CPU power and temperature are not available.' `
        -ForegroundColor Yellow
    Write-Host 'The profiler will refuse to run until they are -- see the check above.' `
        -ForegroundColor Yellow
}
exit $diagnoseCode
