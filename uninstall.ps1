<#
.SYNOPSIS
    Removes what install.ps1 installed: the `profiler` command and its PATH entry.

.DESCRIPTION
    The mirror image of install.ps1. It:

      1. deletes the `profiler.cmd` shim, and the install folder if it is left
         empty,
      2. deletes the profiler's own virtual environment, taking its copies of
         psutil, pandas, matplotlib and numpy with it,
      3. takes the install folder back off the user PATH,
      4. clears the leftovers of older revisions -- the LibreHardwareMonitor
         copy and the elevated `ProfilerHardwareMonitor` logon task, neither of
         which the current build creates,
      5. optionally pip-uninstalls the Python dependencies (-RemovePackages),
         for installs that predate the private environment or were made with
         -NoVenv.

    Like the installer, it needs no Administrator rights. The one exception is
    the legacy scheduled task: it was registered elevated, so deleting it can
    ask for elevation. The script says so rather than failing silently.

    What it deliberately does NOT touch:

      * the repo -- this script lives in it; delete the folder yourself,
      * profiling output (`logs\`, CSVs, PNGs, JSON sidecars) -- that is your
        data, not part of the installation,
      * Python itself, including one this machine only has because the
        installer offered to install it: it is a general-purpose runtime, and
        by now other things may depend on it,
      * Python packages outside the profiler's own environment, unless you
        pass -RemovePackages. psutil, pandas, matplotlib and numpy are shared
        libraries that other projects on this machine are likely to be using.

.EXAMPLE
    .\Uninstall-Profiler.cmd

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -RemovePackages -Force
#>
[CmdletBinding()]
param(
    # Must match the -InstallDir the install ran with; this is that default.
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\profiler",

    # Off by default: these are general-purpose packages, not profiler-private.
    [switch]$RemovePackages,

    # Skip the confirmation prompt (for scripted or non-interactive removal).
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

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
        `schtasks /query` on a machine with no such task writes exactly that,
        which would abort the uninstall over the entirely normal case of there
        being no legacy task to remove. $ErrorActionPreference is scoped
        dynamically, so setting it here covers the call and nothing else.
    #>
    param([scriptblock]$Command, [switch]$ShowOutput)
    $ErrorActionPreference = 'Continue'
    # Out-Host, not a bare call: anything the command writes to the success
    # stream would otherwise become part of this function's output, and the
    # caller would receive pip's entire log with the exit code appended.
    if ($ShowOutput) { & $Command | Out-Host } else { & $Command 2>&1 | Out-Null }
    return $LASTEXITCODE
}

$removed = @()
$skipped = @()

Write-Host "Profiler removal" -ForegroundColor White
Write-Host "================" -ForegroundColor White
Write-Info "Install folder: $InstallDir"

if (-not $Force) {
    Write-Host ''
    Write-Host 'This removes the `profiler` command, its PATH entry and its private'
    Write-Host 'Python environment.'
    if ($RemovePackages) {
        Write-Warn 'It will ALSO pip-uninstall psutil, pandas, matplotlib and numpy'
        Write-Warn 'from your own Python, which other projects may depend on.'
    }
    Write-Host 'Your repo, your profiling output and Python itself are left alone.'
    $answer = Read-Host 'Continue? [y/N]'
    if ($answer -notmatch '^(y|yes)$') {
        Write-Host 'Nothing was changed.'
        exit 1
    }
}

# --------------------------------------------------------------------- shim
Write-Step 'Removing the `profiler` command'
$shim = Join-Path $InstallDir 'profiler.cmd'
if (Test-Path $shim) {
    Remove-Item -LiteralPath $shim -Force
    Write-Ok "Deleted $shim"
    $removed += 'profiler.cmd shim'
} else {
    # Not a problem worth reporting: an uninstall run twice, or run on a
    # machine that was never set up, should finish quietly.
    Write-Info "No shim at $shim (already gone)."
}

# ---------------------------------------------------------------------- venv
# Unlike the packages below, this one is not optional and needs no prompt: the
# environment is profiler-private, created by the installer, and nothing else
# on the machine can be importing from it.
Write-Step "Removing the profiler's own environment"
$venvDir = Join-Path $InstallDir 'venv'
if (Test-Path $venvDir) {
    $size = (Get-ChildItem -LiteralPath $venvDir -Recurse -File -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    Remove-Item -LiteralPath $venvDir -Recurse -Force
    Write-Ok ("Deleted $venvDir ({0:N1} MB, including its psutil, pandas, matplotlib and numpy)" -f ($size / 1MB))
    $removed += 'private virtual environment'
} else {
    Write-Info "No environment at $venvDir (installed with -NoVenv, or an older revision)."
}

# ------------------------------------------------------- legacy: monitor task
# Older revisions ran LibreHardwareMonitor as an elevated at-logon task. The
# current build reads everything from PDH counters, so nothing registers this.
Write-Step 'Checking for the legacy hardware-monitor task'
$taskName = 'ProfilerHardwareMonitor'
if ((Invoke-Native { schtasks /query /tn $taskName }) -eq 0) {
    Write-Info "Found the leftover $taskName task; deleting it..."
    if ((Invoke-Native { schtasks /delete /tn $taskName /f }) -eq 0) {
        Write-Ok "Deleted the $taskName scheduled task."
        $removed += "$taskName scheduled task"
    } else {
        # It was registered with elevated rights, so a standard-user delete is
        # refused. Nothing else here needs elevation, so say so and carry on.
        Write-Warn "Could not delete $taskName -- it was registered elevated."
        Write-Warn 'Run this in an Administrator terminal to remove it:'
        Write-Warn "    schtasks /delete /tn $taskName /f"
        $skipped += "$taskName task (needs elevation)"
    }
} else {
    Write-Info 'None registered.'
}

# ------------------------------------------------- legacy: LibreHardwareMonitor
Write-Step 'Checking for a leftover LibreHardwareMonitor copy'
$lhmDir = Join-Path $InstallDir 'LibreHardwareMonitor'
if (Test-Path $lhmDir) {
    # Stop it first: a running exe cannot have its own folder deleted.
    Get-Process -Name 'LibreHardwareMonitor' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    $size = (Get-ChildItem -LiteralPath $lhmDir -Recurse -File -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    Remove-Item -LiteralPath $lhmDir -Recurse -Force
    Write-Ok ("Deleted $lhmDir ({0:N1} MB)" -f ($size / 1MB))
    $removed += 'LibreHardwareMonitor folder'
} else {
    Write-Info 'None found.'
}

# ------------------------------------------------------------ install folder
if (Test-Path $InstallDir) {
    # Only if we left it empty. A user-chosen -InstallDir may hold other tools,
    # and this uninstaller has no business deleting those.
    $leftovers = @(Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction SilentlyContinue)
    if ($leftovers.Count -eq 0) {
        Remove-Item -LiteralPath $InstallDir -Force
        Write-Ok "Removed the now-empty $InstallDir"
    } else {
        Write-Info "Kept $InstallDir -- it still holds $($leftovers.Count) other item(s)."
    }
}

# ----------------------------------------------------------------------- PATH
Write-Step 'Taking the install folder off your user PATH'

# Read the raw registry value, not [Environment]::GetEnvironmentVariable: that
# expands %VARS% on the way out, so writing the result back would bake today's
# values into entries the user wrote as variables.
$key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
try {
    $raw = $key.GetValue('Path', '',
        [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)

    if ([string]::IsNullOrEmpty($raw)) {
        Write-Info 'Your user PATH is empty; nothing to remove.'
    } else {
        $wanted = $InstallDir.TrimEnd('\')
        # Keep every other entry verbatim, including any empties -- tidying
        # those would be a change the user did not ask for.
        $entries = $raw -split ';'
        $kept = @($entries | Where-Object { $_.TrimEnd('\') -ine $wanted })

        if ($kept.Count -eq $entries.Count) {
            Write-Info "$InstallDir was not on your user PATH."
        } else {
            $newPath = $kept -join ';'
            $kind = $key.GetValueKind('Path')   # preserve REG_EXPAND_SZ vs REG_SZ
            $key.SetValue('Path', $newPath, $kind)
            Write-Ok "Removed $InstallDir from your user PATH."
            $removed += 'user PATH entry'

            # A direct registry write does not notify anyone, so already-open
            # programs keep the old PATH until they restart. Broadcasting
            # WM_SETTINGCHANGE is what SetEnvironmentVariable does internally.
            if (-not ('ProfilerUninstall.Native' -as [type])) {
                Add-Type -Namespace ProfilerUninstall -Name Native -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true, CharSet = System.Runtime.InteropServices.CharSet.Auto)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr hWnd, uint Msg, System.IntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out System.IntPtr lpdwResult);
'@
            }
            $result = [IntPtr]::Zero
            # HWND_BROADCAST = 0xffff, WM_SETTINGCHANGE = 0x1A, SMTO_ABORTIFHUNG = 0x2
            [void][ProfilerUninstall.Native]::SendMessageTimeout(
                [IntPtr]0xffff, 0x1A, [IntPtr]::Zero, 'Environment', 0x2, 5000, [ref]$result)
        }
    }
} finally {
    $key.Dispose()
}

# ------------------------------------------------------------------- packages
Write-Step 'Python dependencies outside that environment'
if ($RemovePackages) {
    # Only reaches your own site-packages. A current install keeps its packages
    # in the venv deleted above, so this finds nothing to do unless the profiler
    # was installed with -NoVenv or by a revision that predates the venv.
    $python = $null
    foreach ($candidate in @('python', 'py')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try { $resolved = & $cmd.Source -c "import sys; print(sys.executable)" 2>$null } catch { continue }
        if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path $resolved)) {
            $python = $resolved.Trim()
            break
        }
    }
    if (-not $python) {
        Write-Warn 'No Python interpreter found on PATH; skipping the package removal.'
        $skipped += 'pip packages (no interpreter found)'
    } else {
        Write-Info "Using $python"
        # `wmi` is in this list because an older revision of the profiler was
        # the only thing that pulled it in. pywin32 is not: it came along as a
        # dependency of `wmi`, but it is shared far too widely to remove here.
        # pip warns on stderr about anything already absent, which is routine
        # here -- Invoke-Native keeps that from being read as a failure.
        $pipCode = Invoke-Native -ShowOutput {
            & $python -m pip uninstall -y psutil pandas matplotlib numpy wmi
        }
        if ($pipCode -eq 0) {
            Write-Ok 'Uninstalled psutil, pandas, matplotlib, numpy (and legacy wmi).'
            $removed += 'pip packages'
        } else {
            Write-Warn 'pip reported a problem; check its output above.'
            $skipped += 'pip packages (pip failed)'
        }
        Write-Info 'pywin32 was left installed: it is a shared package, not profiler-specific.'
        Write-Info "Remove it yourself with:  $python -m pip uninstall -y pywin32"
    }
} else {
    Write-Info 'Left alone. The profiler kept its own copies in the environment just'
    Write-Info 'deleted; any psutil/pandas/matplotlib/numpy in your Python is yours.'
    Write-Info 'Pass -RemovePackages to uninstall those too.'
}

# -------------------------------------------------------------------- summary
Write-Host ''
if ($removed.Count -eq 0) {
    Write-Host 'Nothing was installed; there was nothing to remove.' -ForegroundColor Green
} else {
    Write-Host 'Uninstall complete.' -ForegroundColor Green
    Write-Host 'Removed:'
    foreach ($item in $removed) { Write-Host "  - $item" }
}
if ($skipped.Count -gt 0) {
    Write-Host 'Needs your attention:' -ForegroundColor Yellow
    foreach ($item in $skipped) { Write-Host "  - $item" -ForegroundColor Yellow }
}
Write-Host ''
Write-Host 'Your repo folder and any profiling output were left untouched.'
Write-Host 'Open a new terminal: `profiler` will no longer be on PATH.'
exit 0
