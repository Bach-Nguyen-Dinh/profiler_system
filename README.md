# Profiler System — Windows

A system profiler for Windows. It runs a target Python script as a subprocess
while a background thread samples CPU, memory, per-core frequency, power and
temperature, then charts the result and files everything into a timestamped
folder.

> **Branch note.** This is the `dev_windows` branch: **Windows only**. The Linux
> build lives on `dev` and reads the same metrics out of `/sys`. Neither branch
> tries to be cross-platform — running this one on Linux exits with a message
> pointing at `dev`.

## Requirements

- Windows 10 or 11
- Python 3.8+
- `pip install -r requirements.txt` (psutil, pandas, matplotlib, numpy)
- Optional, for power and temperature: `pip install wmi` plus
  [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
  running as Administrator — see [CPU power and temperature](#cpu-power-and-temperature)

No Administrator rights are needed for anything else.

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
  power, temperature : UNAVAILABLE - the `wmi` package is not installed (pip install wmi)
  topology           : non-hybrid CPU (4 physical cores, 8 logical processors)
```

**Smoke test** — four phases (idle / CPU burn / memory growth / mixed), so every
chart shows clearly different regions:

```powershell
python analyzer.py dummy_workload.py -- --seconds 5 --workers 4
```

## Installing the `profiler` command

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

This writes a `profiler.cmd` shim to `%LOCALAPPDATA%\Programs\profiler` and adds
that folder to your **user** PATH — no Administrator rights required. Open a new
terminal afterwards, then:

```powershell
profiler <target_script.py> [profiler options] -- [target script args]
profiler diagnose
```

The shim hard-codes both the repo path and the interpreter found at install
time. Re-run `install.ps1` if you move the repo or switch virtualenv.

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

## Catches when running on Windows

Everything below is a real difference from the Linux build, not a hypothetical.

### 1. There is no user-mode power counter

Linux reads CPU energy from `/sys/class/powercap/intel-rapl:0/energy_uj`. The
same RAPL registers exist on Windows silicon but live behind MSRs that only a
signed kernel driver can read. **Administrator rights alone do not expose them** —
there is no file to grant permission on, so the Linux
`allow_cpu_power_metric_capture` / udev setup has no Windows equivalent. That
command does not exist on this branch; `diagnose` replaces it.

### 2. `psutil` has no temperature support on Windows

`psutil.sensors_temperatures()` is Linux/FreeBSD-only — the attribute is simply
absent here, so code that calls it raises `AttributeError` rather than returning
empty.

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
that hijacks the name when real Python is not installed. The profiler launches
the target with `sys.executable`, so the target always inherits the same
interpreter and virtualenv as the profiler.

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

These two columns need an external source. Both come from LibreHardwareMonitor
over WMI:

1. `pip install wmi` (pulls in pywin32)
2. Install [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
3. Launch it **as Administrator** — it loads a kernel driver to read the MSRs,
   which is exactly the privileged step Python cannot do on its own
4. Leave it running while you profile

The older OpenHardwareMonitor is accepted as a fallback. Verify with
`python analyzer.py diagnose`; each run's JSON sidecar records which provider was
used. Without this, the power and temperature charts render as an explicit
"unavailable" panel rather than a misleading flat line at zero.

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
  hardware.py           PDH per-core frequency, CPU topology, LHM/OHM power & temperature
  metrics.py            SystemMetricsLogger — the sampling thread and CSV writer
  plotting.py           the six panels and the dashboard
  logs.py               filing output into logs/<timestamp>/
dummy_workload.py       four-phase smoke-test workload
install.ps1             installs the `profiler` command
```

The pipeline in `analyze_workflow`: start the sampler → run the target as a
subprocess → stop and flush → plot → organize. Everything after the target runs
in a `finally` block.

There is no test suite or linter.
