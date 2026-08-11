<#
.SYNOPSIS
    Installs a `profiler` command that points at this copy of analyzer.py.

.DESCRIPTION
    Writes a small shim to %LOCALAPPDATA%\Programs\profiler and puts that folder
    on the *user* PATH, so no Administrator rights are needed. The shim hard-codes
    both the interpreter and the repo path found at install time -- re-run this
    script if you move the repo or switch virtualenv.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\profiler"
)

$ErrorActionPreference = 'Stop'

$repoDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$analyzer = Join-Path $repoDir 'analyzer.py'

if (-not (Test-Path $analyzer)) {
    throw "analyzer.py not found at $analyzer"
}

# --- interpreter ------------------------------------------------------------
# Resolve `python` now and bake the full path in, so the shim does not fall foul
# of the Microsoft Store python.exe alias stub that ships enabled on Windows 11.
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { $pythonCmd = Get-Command py -ErrorAction SilentlyContinue }
if (-not $pythonCmd) {
    throw "No Python interpreter found on PATH. Install Python 3 from python.org and re-run."
}
$python = $pythonCmd.Source
Write-Host "Using interpreter: $python"

# --- dependencies -----------------------------------------------------------
Write-Host "Checking Python dependencies..."
$check = @'
import importlib.util, sys
required = ["psutil", "pandas", "matplotlib", "numpy"]
missing = [p for p in required if importlib.util.find_spec(p) is None]
if missing:
    print("MISSING:" + " ".join(missing))
    sys.exit(1)
print("All required packages found.")
optional = [p for p in ["wmi"] if importlib.util.find_spec(p) is None]
if optional:
    print("Optional (CPU power/temperature): " + " ".join(optional) + " not installed")
'@
$check | & $python -
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Install the missing packages with:  $python -m pip install psutil pandas matplotlib numpy"
    throw "Dependency check failed."
}

# --- shim -------------------------------------------------------------------
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$shim = Join-Path $InstallDir 'profiler.cmd'
@"
@echo off
"$python" "$analyzer" %*
"@ | Out-File -FilePath $shim -Encoding ascii -Force

Write-Host "Installed: $shim"

# --- PATH -------------------------------------------------------------------
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -split ';' -notcontains $InstallDir) {
    $newPath = if ([string]::IsNullOrEmpty($userPath)) { $InstallDir } else { "$userPath;$InstallDir" }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Host "Added $InstallDir to your user PATH (open a new terminal to pick it up)."
} else {
    Write-Host "$InstallDir is already on your user PATH."
}

Write-Host ""
Write-Host "Usage:"
Write-Host "  profiler <target_script.py> [options] -- [target script args]"
Write-Host "  profiler diagnose        # show which metric sources this machine supports"
