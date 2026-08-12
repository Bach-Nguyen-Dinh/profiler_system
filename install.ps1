<#
.SYNOPSIS
    Sets up everything the profiler needs, then installs a `profiler` command.

.DESCRIPTION
    Run this once. It:

      1. finds a Python interpreter -- and offers to install one if there is
         none,
      2. creates the profiler's own virtual environment under the install
         folder and pip installs requirements.txt into it,
      3. writes a `profiler` shim to %LOCALAPPDATA%\Programs\profiler and puts
         that folder on the user PATH,
      4. verifies the result with `analyzer.py diagnose`.

    Nothing here needs Administrator rights, and nothing is left running in the
    background. Every metric the profiler samples -- CPU, memory, per-core
    frequency, package power and temperature -- comes from Windows performance
    counters read directly through ctypes, so there is no monitoring service to
    install, no kernel driver, and no logon task.

    The private environment means the profiler's own libraries (psutil, pandas,
    matplotlib, numpy) never touch your site-packages, and uninstalling is a
    folder delete. It does NOT change which interpreter your profiled scripts
    run under: analyzer.py detects that it is running from this environment and
    launches the target with the `python` on your PATH instead, so a script
    still sees its own project's dependencies. Pass -NoVenv to install into the
    interpreter directly, the way older revisions did.

    The shim hard-codes both the interpreter and the repo path found at install
    time -- re-run this script if you move the repo.

.EXAMPLE
    .\Install-Profiler.cmd

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir D:\tools\profiler

.EXAMPLE
    # Unattended: install Python too if it is missing, without prompting.
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallPython
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\profiler",

    # Install Python (per-user, via winget) without asking, when none is found.
    [switch]$InstallPython,

    # Never install Python; fail with instructions instead. Both switches exist
    # for scripted runs, where there is nobody to answer the prompt.
    [switch]$NoInstallPython,

    # Install the packages into the interpreter itself rather than into a
    # private environment. Your site-packages, your call.
    [switch]$NoVenv
)

$ErrorActionPreference = 'Stop'

# The Python release winget installs when the machine has none.
$PythonWingetId = 'Python.Python.3.12'
$PythonMinimum = '3.8'

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
function Write-Warn { param([string]$Text) Write-Host "    $Text" -ForegroundColor Yellow }

function Invoke-Native {
    <#
        Run a native command and hand back only its exit code.

        Necessary because under $ErrorActionPreference='Stop', Windows
        PowerShell promotes anything a native command writes to stderr into a
        terminating error -- and redirecting the stream does not suppress that.
        Both `winget` and `pip` write routine progress and warnings there, so
        without this a perfectly successful install would abort partway.
        $ErrorActionPreference is scoped dynamically, so setting it here covers
        the call and nothing else.
    #>
    param([scriptblock]$Command, [switch]$ShowOutput)
    $ErrorActionPreference = 'Continue'
    # Out-Host, not a bare call: anything the command writes to the success
    # stream would otherwise become part of this function's output, and the
    # caller would receive pip's entire log with the exit code appended.
    if ($ShowOutput) { & $Command | Out-Host } else { & $Command 2>&1 | Out-Null }
    return $LASTEXITCODE
}

# --------------------------------------------------------- interpreter lookup
function Resolve-Interpreter {
    <#
        Turn a candidate command into the real interpreter behind it, or $null.

        Running the candidate is the check: it resolves `py` to the interpreter
        it launches, and it is what rejects the Microsoft Store python.exe
        alias stub that ships enabled on Windows 11 -- that stub opens the
        Store and produces no output, so the shim can never end up pointing at
        it. The probe deliberately contains no double quotes; Windows
        PowerShell does not reliably escape those when passing an argument to a
        native program.
    #>
    param([string]$Candidate)

    # A probe that is not an interpreter can fail in several ways -- missing
    # file, stderr output (terminating under 'Stop'), a non-zero exit. None of
    # them is an error here; they all just mean "not this one".
    $ErrorActionPreference = 'Continue'

    $probe = 'import sys; print(sys.executable); print(sys.version.split()[0]); print(1 if sys.version_info[:2] >= (3, 8) else 0)'
    try { $lines = @(& $Candidate -c $probe 2>$null) } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or $lines.Count -lt 3) { return $null }

    $exe = $lines[0].Trim()
    if (-not $exe -or -not (Test-Path $exe)) { return $null }
    return [pscustomobject]@{
        Path      = $exe
        Version   = $lines[1].Trim()
        Supported = ($lines[2].Trim() -eq '1')
    }
}

function Get-CandidatePythonPath {
    <#
        Where a Python we just installed might be, given that this process
        cannot see it yet.

        A running program holds a snapshot of PATH taken when it started, so an
        interpreter installed a moment ago is invisible to Get-Command until a
        new terminal is opened. Read the registry PATH, and check the standard
        per-user install root directly.
    #>
    $paths = @()

    # Expanding %VARS% is fine here -- these values are only read, never
    # written back (which is what would bake today's values into the PATH).
    $registryPath = @(
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        [Environment]::GetEnvironmentVariable('Path', 'Machine')
    ) -join ';'
    foreach ($dir in ($registryPath -split ';')) {
        if ([string]::IsNullOrWhiteSpace($dir)) { continue }
        $exe = Join-Path $dir.Trim() 'python.exe'
        if (Test-Path $exe) { $paths += $exe }
    }

    foreach ($glob in @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
                        "$env:ProgramFiles\Python3*\python.exe")) {
        $paths += @(Get-ChildItem -Path $glob -ErrorAction SilentlyContinue |
                    ForEach-Object { $_.FullName })
    }
    return $paths
}

function Find-Python {
    param([string[]]$ExtraPaths = @())

    $candidates = @()
    foreach ($name in @('python', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $candidates += $cmd.Source }
    }
    $candidates += $ExtraPaths

    $unsupported = $null
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not $candidate) { continue }
        $found = Resolve-Interpreter $candidate
        if (-not $found) { continue }
        if ($found.Supported) { return $found }
        # Keep looking: another entry on PATH may be new enough.
        if (-not $unsupported) { $unsupported = $found }
    }
    if ($unsupported) {
        Write-Warn ("Found Python $($unsupported.Version) at $($unsupported.Path), " +
                    "but this profiler needs $PythonMinimum or newer.")
    }
    return $null
}

function Install-Python {
    <#
        Install Python per-user with winget, then find it.

        --scope user keeps the whole installer unelevated, which is the point:
        an elevated install would put the pip packages, the shim and the PATH
        entry in the administrator's profile rather than this user's.
    #>
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warn 'winget is not available on this machine (it ships with Windows 11'
        Write-Warn 'and Windows 10 1809+), so Python cannot be installed automatically.'
        return $null
    }

    Write-Info "Running: winget install --id $PythonWingetId --scope user"
    Write-Info 'This downloads from python.org via winget and takes a minute or two.'
    $code = Invoke-Native -ShowOutput {
        winget install --id $PythonWingetId --scope user --source winget `
               --accept-package-agreements --accept-source-agreements --silent
    }
    # winget reports non-zero for plenty of non-failures ("already installed",
    # "no applicable upgrade"), so the verdict is whether an interpreter is now
    # findable -- not this exit code.
    if ($code -ne 0) {
        Write-Info "winget exited with code $code; checking for an interpreter anyway..."
    }
    return (Find-Python -ExtraPaths (Get-CandidatePythonPath))
}

function Request-Python {
    <#
        Decide what to do about a machine with no usable Python.

        Installing a language runtime is a much larger footprint than the four
        pip packages this installer otherwise adds, and the uninstaller will
        not take it away again -- so it is a question, not a default.
    #>
    $answer = if ($InstallPython)        { 'i' }
              elseif ($NoInstallPython)  { 'c' }
              elseif (-not [Environment]::UserInteractive) { 'c' }
              else {
                  Write-Host ''
                  Write-Warn "No working Python $PythonMinimum+ interpreter was found."
                  Write-Host ''
                  Write-Host '  [I] Install Python for me now (per-user, no Administrator rights)'
                  Write-Host '  [O] Open the download page so I can do it myself, and stop here'
                  Write-Host '  [C] Cancel'
                  Write-Host ''
                  Write-Info 'Python is a general-purpose runtime, so Uninstall-Profiler.cmd'
                  Write-Info 'will not remove it again.'
                  Write-Host ''
                  $reply = (Read-Host 'Choose [I/o/c]').Trim().ToLower()
                  if ($reply) { $reply } else { 'i' }
              }

    $manual = ("Install Python $PythonMinimum+ from https://www.python.org/downloads/windows/ " +
               "(tick 'Add python.exe to PATH') and run this installer again. " +
               "Or re-run with -InstallPython to have this script install it for you.")

    switch -Regex ($answer) {
        '^i' {
            Write-Step 'Installing Python'
            $installed = Install-Python
            if (-not $installed) { throw "Python could not be installed automatically. $manual" }
            Write-Info 'Your PATH now has Python on it, but this already-running installer'
            Write-Info 'cannot see that, so it uses the new interpreter by full path.'
            return $installed
        }
        '^o' {
            Start-Process 'https://www.python.org/downloads/windows/'
            throw "Opened the Python download page. $manual"
        }
        default { throw "No Python interpreter. $manual" }
    }
}

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
$python = Find-Python
if (-not $python) { $python = Request-Python }
Write-Ok "Python $($python.Version) at $($python.Path)"

# ------------------------------------------------------------- environment
$venvDir = Join-Path $InstallDir 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if ($NoVenv) {
    Write-Step 'Installing into your Python directly (-NoVenv)'
    Write-Info "Packages will go into $($python.Path)"
    $runtime = $python.Path
    $allowUserFallback = $true
} else {
    Write-Step "Creating the profiler's own environment"
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    if (Test-Path $venvPython) {
        Write-Info "Reusing the environment already in $venvDir"
    } else {
        $venvCode = Invoke-Native -ShowOutput { & $python.Path -m venv $venvDir }
        if ($venvCode -ne 0 -or -not (Test-Path $venvPython)) {
            throw ("Could not create a virtual environment in $venvDir. " +
                   "Re-run with -NoVenv to install the packages into " +
                   "$($python.Path) instead.")
        }
        Write-Ok "Created $venvDir"
    }

    # analyzer.py looks for this marker beside the interpreter (sys.prefix) to
    # recognise that it is running from the profiler's environment rather than
    # the user's, and therefore that the target script must NOT inherit it.
    $marker = Join-Path $venvDir '.profiler-venv'
    @"
The profiler's own virtual environment, created by install.ps1.

analyzer.py checks for this file next to the interpreter (sys.prefix) to tell
that it is running from the profiler's environment rather than yours. When it
finds it, the profiled script is launched with the python on your PATH instead
of this one -- otherwise every target would run in here, where its own
dependencies do not exist.

Repo:        $repoDir
Created:     $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Created by:  $($python.Path) (Python $($python.Version))

Delete this folder, or run Uninstall-Profiler.cmd, to remove it.
"@ | Out-File -FilePath $marker -Encoding utf8 -Force

    $runtime = $venvPython
    # --user is rejected inside a virtual environment, and pointless: the venv
    # is always writable by the user who owns it.
    $allowUserFallback = $false
}

# -------------------------------------------------------------- dependencies
Write-Step 'Installing Python dependencies'
$requirements = Join-Path $repoDir 'requirements.txt'
if (-not (Test-Path $requirements)) { throw "requirements.txt not found in $repoDir" }

if ((Invoke-Native { & $runtime -m pip --version }) -ne 0) {
    Write-Info 'pip is missing; bootstrapping it with ensurepip...'
    Invoke-Native -ShowOutput { & $runtime -m ensurepip --default-pip } | Out-Null
}

$pipCode = Invoke-Native -ShowOutput {
    & $runtime -m pip install --disable-pip-version-check -r $requirements
}
if ($pipCode -ne 0 -and $allowUserFallback) {
    # A system-wide interpreter (Program Files, or the one shipped by an IDE)
    # is not writable by a standard user; --user targets the profile instead.
    Write-Info 'Retrying the install into your user site-packages...'
    $pipCode = Invoke-Native -ShowOutput {
        & $runtime -m pip install --disable-pip-version-check --user -r $requirements
    }
}
if ($pipCode -ne 0) { throw 'pip could not install the dependencies.' }

$verify = @'
import importlib.util, sys
missing = [p for p in ["psutil", "pandas", "matplotlib", "numpy"]
           if importlib.util.find_spec(p) is None]
if missing:
    print("still missing: " + " ".join(missing))
    sys.exit(1)
'@
$verify | & $runtime -
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
"$runtime" "$analyzer" %*
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
& $runtime $analyzer diagnose
$diagnoseCode = $LASTEXITCODE

Write-Host ''
if ($diagnoseCode -eq 0) {
    Write-Host 'Setup complete.' -ForegroundColor Green
    Write-Host ''
    Write-Host 'In a NEW terminal:'
    Write-Host '  profiler <target_script.py> [options] -- [target script args]'
    Write-Host '  profiler diagnose'
    if (-not $NoVenv) {
        Write-Host ''
        Write-Host 'Profiled scripts run under the `python` on your PATH, not the'
        Write-Host 'environment above, so they keep their own dependencies. Override'
        Write-Host 'that per run with:  profiler --python C:\path\to\python.exe <script.py>'
    }
} else {
    Write-Host 'Setup finished, but CPU power and temperature are not available.' `
        -ForegroundColor Yellow
    Write-Host 'The profiler will refuse to run until they are -- see the check above.' `
        -ForegroundColor Yellow
}
exit $diagnoseCode
