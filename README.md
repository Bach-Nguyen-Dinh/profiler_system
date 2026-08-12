# Profiler System — Windows

A system profiler for Windows. It runs a target Python script as a subprocess
while a background thread samples CPU, memory, per-core frequency, power and
temperature, then charts the result and files everything into a timestamped
folder.

> **Branch note.** This is the `dev_windows` branch: **Windows only**. The Linux
> build lives on `dev` and reads the same metrics out of `/sys`. Neither branch
> tries to be cross-platform — running this one on Linux exits with a message
> pointing at `dev`.

## Install

**Double-click `Install-Profiler.cmd`.** That is the whole installation. It:

1. finds your Python interpreter — and offers to install one if you have none,
2. creates the profiler's own environment and `pip install`s `requirements.txt`
   into it,
3. installs a `profiler` command on your PATH,
4. verifies the lot with `analyzer.py diagnose`.

Open a new terminal when it finishes, and `profiler <script.py>` works.

**No Administrator rights, no background service, no kernel driver.** Every
metric — CPU, memory, per-core frequency, package power, temperature — is a
Windows performance counter read through `ctypes`. There is nothing to keep
running while you profile.

**Nothing lands in your site-packages.** `psutil`, `pandas`, `matplotlib` and
`numpy` go into a private virtual environment under the install folder, so the
profiler cannot disturb versions your own projects depend on, and uninstalling
is a folder delete. Your profiled scripts do **not** run in that environment —
see [Which interpreter runs your script](#which-interpreter-runs-your-script).

**If you have no Python at all**, the installer says so and offers to install it
for you (per-user, via `winget`, still no Administrator rights) rather than just
printing a link. It asks first, because a language runtime is a far bigger
change to your machine than four pip packages — and `Uninstall-Profiler.cmd`
will not remove it again. Answer `O` to get the download page instead, or `C` to
stop. Scripted runs can pass `-InstallPython` or `-NoInstallPython` to skip the
question; with neither, a non-interactive run stops with instructions.

Prefer a real executable? `powershell -ExecutionPolicy Bypass -File .\build_installer.ps1`
compiles the same script into `dist\ProfilerSetup.exe`. Put it next to
`analyzer.py` and double-click that instead.

Options, if you need them:

| | |
|---|---|
| `Install-Profiler.cmd -InstallDir D:\tools\profiler` | install somewhere other than `%LOCALAPPDATA%\Programs\profiler` |
| `Install-Profiler.cmd -InstallPython` | install Python too if it is missing, without asking |
| `Install-Profiler.cmd -NoInstallPython` | never install Python; stop with instructions instead |
| `Install-Profiler.cmd -NoVenv` | install the packages into your Python instead of a private environment |

**Requirements:** Windows 10 or 11, and an internet connection at install time.
Python 3.8+ — the installer offers to get it if you have none.

## Uninstall

**Double-click `Uninstall-Profiler.cmd`.** It deletes the `profiler` command and
its private environment, takes the install folder back off your user PATH, and
clears the leftovers of older revisions (the LibreHardwareMonitor copy and the
`ProfilerHardwareMonitor` logon task, neither of which the current build
creates). No Administrator rights, same as the install.

It leaves alone, on purpose:

- **this repo** — the uninstaller lives in it; delete the folder yourself,
- **your profiling output** — `logs\`, CSVs, PNGs and JSON sidecars are data,
  not installation,
- **Python itself**, including one installed by the installer's offer — it is a
  general-purpose runtime, and by now other things may be using it,
- **Python packages outside the private environment** — `psutil`, `pandas`,
  `matplotlib` and `numpy` in *your* Python are general-purpose libraries your
  other projects are likely using. The profiler's own copies live in the
  environment above and go with it.

| | |
|---|---|
| `Uninstall-Profiler.cmd -RemovePackages` | pip-uninstall those four from your own Python as well (plus the legacy `wmi`) — only relevant after a `-NoVenv` install, or one made by a revision predating the private environment |
| `Uninstall-Profiler.cmd -InstallDir D:\tools\profiler` | match a non-default install location |
| `Uninstall-Profiler.cmd -Force` | skip the confirmation prompt |

Running it twice is harmless, and it never deletes the install folder itself
unless removing the shim left it empty — a folder you chose yourself may hold
other tools.

## Usage

```powershell
python analyzer.py <target_script.py> [profiler options] -- [target script args]
```

**Profiler options**

| Option | Default | Meaning |
|---|---|---|
| `--metrics_interval_ms` | 500 | sampling interval in milliseconds |
| `--output_dir` | the target script's directory | where output is written |
| `--csv_write_interval_s` | 5 | how often buffered samples are flushed to the CSV |
| `--python` | the `python` on your PATH, or the current one | interpreter to run the target script with |

The `--` separator is required before any arguments meant for the target script.

**Example**

```powershell
python analyzer.py train.py --metrics_interval_ms 250 -- --epochs 2 --batch_size 16
```

**Check what your machine can measure**

```powershell
python analyzer.py diagnose
```

```
Profiler capability check
========================================
  per-core frequency : PDH performance counters (base clock 2803 MHz)
  CPU power          : PDH Energy Meter (RAPL): RAPL_Package0_PKG
  CPU temperature    : ACPI thermal zone: \_TZ.TZ00
                       (firmware-reported zone, not the on-die sensor)
  topology           : non-hybrid CPU (4 physical cores, 8 logical processors)

All required metric sources are available.
```

It exits non-zero only if **CPU power** is missing, the one metric a run cannot
go ahead without, so it doubles as the installer's own verification step. A
missing temperature is reported but does not fail the check.

**Smoke test** — four phases (idle / CPU burn / memory growth / mixed), so every
chart shows clearly different regions:

```powershell
python analyzer.py dummy_workload.py -- --seconds 5 --workers 4
```

## The `profiler` command

The installer writes a `profiler.cmd` shim to `%LOCALAPPDATA%\Programs\profiler`
and adds that folder to your **user** PATH. In a new terminal:

```powershell
profiler <target_script.py> [profiler options] -- [target script args]
profiler diagnose
```

The shim hard-codes both the repo path and the profiler's own interpreter.
Re-run the installer if you move the repo.

## Which interpreter runs your script

The profiler and the script it profiles are **two processes, and they do not
have to share an interpreter.** They deliberately do not, once the profiler has
its own environment: that environment contains `psutil`, `pandas`, `matplotlib`
and `numpy` and nothing else, so running your script in it would hide your
script's own dependencies and report the result as your bug.

The target interpreter is picked per run:

1. `--python <path>` if you pass one — `profiler --python .\.venv\Scripts\python.exe train.py`,
2. otherwise the `python` on your **PATH**, whenever the profiler is running
   from its private environment. An activated virtualenv puts itself first on
   PATH, so `profiler train.py` inside your project's venv runs `train.py` in
   that venv without being told to,
3. otherwise the current interpreter. `python analyzer.py train.py` therefore
   behaves exactly as you would expect: profiler and target share whatever
   interpreter you invoked.

Both are recorded in the run's JSON sidecar as `profiler_python` and
`target_python`, and the target's is echoed in the `Running:` line at the start
of the run. Neither a bad `--python` nor a missing PATH interpreter is silent:
the first stops the run before any sampling starts, the second prints a note
saying the target will share the profiler's environment.

## Output

Everything from one run shares a `YYYYmmdd_HHMMSS` stamp and is filed into
`<output_dir>/logs/<timestamp>/`:

| File | Contents |
|---|---|
| `system_metrics_<ts>.csv` | every sample |
| `system_metrics_<ts>.json` | machine description and which sensor sources actually worked |
| `memory_usage_<ts>.png` | memory in GB |
| `cpu_cores_usage_<ts>.png` | per-logical-CPU utilisation |
| `cpu_cores_frequency_<ts>.png` | per-logical-CPU MHz |
| `cpu_power_<ts>.png` | package power in watts |
| `cpu_temperature_<ts>.png` | package temperature in °C |
| `overall_cpu_usage_<ts>.png` | aggregate utilisation |
| `system_metrics_dashboard_<ts>.png` | all six panels on one sheet |

That timestamp is the join key across the whole pipeline. Renaming the CSV, or
adding underscores to its name, breaks plotting and grouping.

**CSV schema:** `Timestamp`, `cpu_usage`, `memory_usage`, `total_memory`,
`swap_usage`, `total_swap`, `core_<N>_usage` per logical CPU,
`core_<N>_frequency` per logical CPU, `cpu_temperature`, `cpu_power`. It matches
the Linux branch, so existing analysis scripts keep working.

A metric the machine cannot supply is written as an **empty cell**, never as
zero — an empty cell means "not measured", which is not the same as 0 watts.
`cpu_power` should never be empty: it is required, so a run whose source is
missing aborts before the target starts rather than producing that CSV at all.
`cpu_temperature` may legitimately be empty for a whole run — see
[CPU power and temperature](#cpu-power-and-temperature). The column is always
present either way, so the schema never changes shape.

## Catches when running on Windows

Everything below is a real difference from the Linux build, not a hypothetical.

### 1. You cannot read the RAPL MSRs — but you do not have to

Linux reads CPU energy from `/sys/class/powercap/intel-rapl:0/energy_uj`. The
same RAPL registers exist on Windows silicon but live behind MSRs that only a
signed kernel driver can read. **Administrator rights alone do not expose
them** — there is no file to grant permission on, so the Linux
`allow_cpu_power_metric_capture` / udev setup has no Windows equivalent. That
command does not exist on this branch; `diagnose` replaces it.

The way round it is that something in the kernel is *already* reading them.
The platform power-engine driver (`intelpep`, inbox on Intel platforms)
republishes the RAPL domains as instances of the PDH `Energy Meter` counter
object:

```
\Energy Meter(RAPL_Package0_PKG)\Power      whole package  <- what we sample
\Energy Meter(RAPL_Package0_PP0)\Power      cores
\Energy Meter(RAPL_Package0_PP1)\Power      integrated graphics
\Energy Meter(RAPL_Package0_DRAM)\Power     memory
```

`Power` is already a rate, in **milliwatts**. Reading it is the Windows
equivalent of opening `energy_uj`, and it needs no third-party program, no
driver of ours and no elevation. It is also *cheaper* than the Linux path:
`dev` sleeps 100 ms inside `get_cpu_power()` to difference an energy counter,
which puts a floor under its sampling rate. Here the driver has already
differentiated, so a sample is one counter read and `--metrics_interval_ms` has
no such floor.

Two things to know if you touch the selection logic in `EnergyMeter._select`:

- **The domains nest.** PP0 (cores) and PP1 (graphics) sit *inside* PKG, so
  summing every instance bills the same watts twice. The code takes the `_PKG`
  instances — one per socket, matching what `intel-rapl:0` reports on Linux —
  and only falls back to the sub-domains when no package instance exists. DRAM
  is never included: that is memory power, not CPU power.
- **`_Total` is not the total.** The rollup instance reads a flat `0.0` on the
  machines checked, and would double-count for the reason above anyway.

Not every machine has this. A VM, an AMD platform with no energy-metering
driver, or a machine with its chipset drivers stripped out has no `Energy
Meter` object at all, and there genuinely is no user-mode substitute. `diagnose`
tells you which case you are in.

Note the neighbouring `Power Meter` counter object is a *different* thing (an
EMI-backed whole-system meter, mostly on Surface-class hardware) and is usually
present-but-empty: adding the counter succeeds and it has no instances. That is
why `hardware.py` decides availability by sampling rather than by whether the
counter opened.

### 2. `psutil` has no temperature support on Windows

`psutil.sensors_temperatures()` is Linux/FreeBSD-only — the attribute is simply
absent here, so code that calls it raises `AttributeError` rather than returning
empty.

Temperature is the metric Windows serves worst, and unlike power there is no
trick that recovers it. The CPU's on-die sensor sits behind the same MSRs as
RAPL, and **nothing in Windows republishes it**. What is left is the ACPI
thermal zones the firmware declares, read from
`\Thermal Zone Information(*)\High Precision Temperature` (tenths of a kelvin);
the profiler takes the hottest zone each sample, since firmware does not label
which zone tracks the CPU.

That is a *platform* number, not a core temperature: coarse, slow, and on some
machines a constant that never moves. The development machine is one of those —
`\_TZ.TZ00` held 27.9 °C through a 20-second all-core burn that took package
power from 9 W to 40 W. Because a flat line on auto-scaled axes still looks like
a measurement, the profiler checks for it: if the zone's spread stays under
0.5 °C while CPU load swings more than 25 points, the run prints a warning, the
sidecar records `"temperature_static": true`, and the temperature chart is
captioned to say so on its face.

And a machine may declare no usable zone at all — common on desktops, servers
and VMs. That does **not** stop a run: temperature is best-effort, so the
column is left empty and everything else is sampled normally.

If you need real die temperatures on Windows, that requires a signed kernel
driver — which is the one thing this build deliberately does not ask you to
install.

### 3. `psutil.cpu_freq(percpu=True)` returns one entry, not one per core

On an 8-logical-CPU machine it returns a single `scpufreq` carrying the *nominal*
clock, not live per-core values. Using it directly would collapse eight frequency
columns into one.

This build instead reads the PDH performance counter
`\Processor Information(*)\% Processor Performance` through `ctypes` — the same
source Task Manager displays — and multiplies by the base clock. It needs no
third-party package and no elevation, and it does capture turbo: the counter
exceeds 100% under boost, which is why measured frequencies can sit well above
the base clock (2803 MHz base → 4594 MHz observed on the development machine).

Two implementation details worth knowing if you touch `profiler/hardware.py`:

- `PdhAddEnglishCounterW` is used rather than `PdhAddCounterW` because counter
  names are localised; the English form is stable on every system language.
- PDH status codes are **unsigned**. Left at the ctypes default `c_int`,
  `PDH_MORE_DATA` (`0x800007D2`) decodes negative, never matches, and every read
  silently returns no data. The restypes are set explicitly for this reason.

### 4. `python3` does not exist

A default Windows install provides `python`, plus a Microsoft Store alias stub
that hijacks the name when real Python is not installed. Nothing here ever
launches a bare `python3`; the target is always started from a resolved
interpreter path.

Resolving is what rejects the Store stub, in both the installer and
`analyzer.py`: ask the candidate to print `sys.executable`. A real interpreter
answers, the stub opens the Store and produces nothing — so a shim can never end
up pointing at it, and neither can a profiled run. Which interpreter the target
gets is [its own question](#which-interpreter-runs-your-script).

### 5. No `os.geteuid`, no `sudo`, no POSIX file modes

- `os.geteuid` does not exist on Windows; an elevation check needs
  `ctypes.windll.shell32.IsUserAnAdmin()`.
- Windows 11 does ship `sudo.exe`, but it is **disabled by default** (Settings →
  System → For developers → Enable sudo) and still raises a UAC prompt each time.
  Nothing in this build needs it.
- The Linux build `chmod`s its CSV to `a+rw` so a `sudo` run leaves readable
  output. Windows files inherit the directory ACL and `os.chmod` only toggles
  the read-only attribute, so that step is dropped.

### 6. Legacy tooling from the Linux branch is not here

Removed on this branch because it cannot work on Windows or was already unwired:

| Removed | Why |
|---|---|
| `setup_rapl_permissions.sh`, `install.sh` | udev rules, `/usr/local/bin` |
| `system_metrics_topaz.py` | reads the `sensors` CLI |
| `power_compare_32_core_16_p_core_cphd/` | toggles `/sys/devices/system/cpu/cpu*/online` via `sudo tee` |
| `histograms/` | one-off analysis with hard-coded `/home/...` paths |
| `integrated_profiler_system.py`, `test_profiler_use.py` | superseded `sys.settrace` profilers, imported by nothing |
| `code_dependencies_analyser.py` | its call site was already commented out; dropping it removes the networkx/pyvis dependency |

All of it is still on `dev`.

### 7. Ctrl+C and crashing targets

A console Ctrl+C reaches both the profiler and the target. Metrics are still
flushed, plotted and filed — those steps run in a `finally` block, so an
interrupted or non-zero-exit target still produces a complete run folder.

### 8. `MPLCONFIGDIR` is no longer pinned

The Linux build pins matplotlib's cache next to the script because under `sudo`
root's cache lands in `/tmp`, which systemd wipes every boot, forcing a ~25 s
font-cache rebuild. Windows caches to `%LOCALAPPDATA%\matplotlib`, which
persists, so the workaround — and its import-ordering constraint — is gone.

## CPU power and temperature

| | Source | Unit | Required? |
|---|---|---|---|
| `cpu_power` | `\Energy Meter(RAPL_Package0_PKG)\Power` | mW → W | **yes** — the real RAPL package counter, same domain Linux reads |
| `cpu_temperature` | `\Thermal Zone Information(*)\High Precision Temperature` | dK → °C | no — firmware ACPI zone, **not** the on-die sensor |

Nothing to install and nothing to run: both are Windows performance counters,
read through `ctypes` in `profiler/hardware.py`. See
[catch 1](#1-you-cannot-read-the-rapl-msrs--but-you-do-not-have-to) for why
power works without a driver and [catch 2](#2-psutil-has-no-temperature-support-on-windows)
for why temperature is the weak one. Verify either with `profiler diagnose`.

**Power is required.** If it is missing the profiler prints what to do and
exits — it does not run the target and hand back a CSV with an empty power
column. That mirrors the Linux build, where an unreadable RAPL counter is fatal
rather than degraded.

**Temperature is not.** A machine whose firmware declares no ACPI thermal zone
has no CPU temperature to give *any* user-mode program, and there is nothing
the user could install to change that — so refusing to profile it would only
throw away a perfectly good power measurement. Such a run goes ahead, the
`cpu_temperature` column is left empty (never zero-filled), the chart says so
on its face, and `diagnose` reports it without failing. This is the one place
`dev_windows` deliberately diverges from `dev`'s "both or nothing" rule, and it
is a hardware fact, not a preference.

Two more notes on how they are wired in:

- Losing a source *mid-run* does not abort — the samples already taken are
  worth keeping. Instead the run warns at the end, the sidecar records
  `sensor_lost` and `sensor_gap_samples`, and the affected chart says so. A
  source that was never available is not counted as a mid-run gap.
- Each run's sidecar records exactly what was sampled: `power_source` and
  `power_domains` (which RAPL instances were summed), `temperature_source`,
  `temperature_zones`, `temperature_available` and `temperature_static` — plus
  `profiler_python` and `target_python`, so a CSV always says which interpreter
  produced the load it measured.

## P-cores vs E-cores

The hybrid P-core / E-core split only exists on Intel 12th gen and newer. On
anything older there are no P-cores or E-cores — every core is the same kind of
core.

This build asks Windows rather than assuming. `GetLogicalProcessorInformationEx`
reports an `EfficiencyClass` per physical core; more than one distinct class
means a hybrid CPU. Only then are cores labelled `P-core N` / `E-core N` in chart
legends, and the mapping comes from the hardware, never from the core index. On a
non-hybrid CPU everything is plain `Core N` and no P/E comparison is produced.

The classification is recorded in each run's JSON sidecar, which is what the
plotting code reads to label the charts.

## Layout

```
analyzer.py             CLI entry point and the whole control flow
profiler/
  hardware.py           every PDH counter: frequency, RAPL power, thermal zone, topology
  metrics.py            SystemMetricsLogger — the sampling thread and CSV writer
  plotting.py           the six panels and the dashboard
  logs.py               filing output into logs/<timestamp>/
dummy_workload.py       four-phase smoke-test workload
Install-Profiler.cmd    double-click entry point for the installer
install.ps1             the installer itself: Python, environment, shim
Uninstall-Profiler.cmd  double-click entry point for the uninstaller
uninstall.ps1           removes the shim, the environment, the PATH entry
build_installer.ps1     compiles install.ps1 into dist\ProfilerSetup.exe
```

The pipeline in `analyze_workflow`: start the sampler → run the target as a
subprocess → stop and flush → plot → organize. Everything after the target runs
in a `finally` block.

There is no test suite or linter.
