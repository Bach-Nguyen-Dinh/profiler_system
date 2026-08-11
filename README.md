# Profiler System

A Python-based system profiling tool that monitors CPU, memory, temperature, and power consumption during program execution.

## Usage

Run the profiler by passing your target script as the first argument, followed by profiler options, then `--`, then any arguments for your target script:

```
python3 profiler_system/analyzer.py <target_script.py> [profiler options] -- [target script args]
```

**Profiler options:**
- `--metrics_interval_ms` — how often to sample metrics in milliseconds (default: 500)
- `--output_dir` — where to write output files (default: target script's directory)
- `--csv_write_interval_s` — how often to flush metrics to CSV in seconds (default: 5)

The `--` separator is required when passing arguments to the target script.

**Example:**

<!-- The "--" separates profiler parameters from target program parameters -->
```bash
python3 profiler_system/analyzer.py sar_colorization.py \
    --metrics_interval_ms 500 \
    --csv_write_interval_s 5 \
    -- \
    --sar_dir prepared_dataset/train/sar/ \
    --optical_dir prepared_dataset/train/optical/ \
    --n_epochs 2 \
    --batch_size 16 \
    --img_size 256 \
    --checkpoint_interval 10
```

## Enabling CPU Power Metrics

CPU power measurement requires a one-time permission setup. If you see a warning like:

```
[Warning] CPU power metrics unavailable: permission denied.
```

Run the following command once:

```bash
sudo python3 profiler_system/analyzer.py allow_cpu_power_metric_capture
```

After this, CPU power metrics will be collected automatically on all future runs without sudo. The setup persists across reboots.

> **Note:** This requires an Intel CPU with RAPL support. On unsupported hardware, power metrics will be silently skipped and all other metrics will still be collected.

## Installing system-wide (`profiler` command)

To run the profiler from anywhere without specifying the full path, use the provided install script. It writes a wrapper to `/usr/local/bin/profiler` that points to `analyzer.py` in this directory.

```bash
sudo bash install.sh
```

The script will:
1. Check that all required Python packages are installed (`psutil`, `matplotlib`, `networkx`, `pyvis`, `pandas`) and list any that are missing.
2. Create `/usr/local/bin/profiler` pointing to `analyzer.py` in this repo.

After installing, you can use `profiler` instead of `python3 profiler_system/analyzer.py`:

```bash
profiler <target_script.py> [profiler options] -- [target script args]
sudo profiler allow_cpu_power_metric_capture
```

**Example:**

```bash
profiler /home/sarthak/workspace/SAR_codebase/cphd_aic.py --metrics_interval_ms 500 --csv_write_interval_s 5 -- --file /home/public/sar/sar-server/data/cphd/2023-10-22-15-20-28_CPHD.cphd 

```
  

> **Note:** The wrapper hard-codes the path to this repo at install time, so keep the repo in the same location after installing. If you move it, re-run `sudo bash install.sh`.

## Histograms (`histograms/`)

The scripts in `histograms/` are standalone post-hoc analysis tools. They are not part of the profiling pipeline — run them afterwards against a CSV a profiling run already produced, to summarize how the cores were distributed across frequency and utilisation ranges.

Every script takes the CSV as its first argument:

```bash
python3 histograms/<script>.py <system_metrics_*.csv> [options]
```

**Options (all scripts):**
- `-o`, `--output_dir` — where to write the PNGs (default: the script's own directory, i.e. `histograms/`)
- `--max_freq` — max CPU frequency in MHz, used to normalize frequencies to a percentage (default: 4000)
- `--plots` — which histograms to generate (default: all; see the table below)
- `--show` — display each plot interactively as well as saving it. Without this, plots are only written to disk.

**Example:**

```bash
python3 histograms/cores_active_histogram.py \
    logs/20260115_154219/system_metrics_20260115_154219.csv \
    --output_dir ~/analysis/january_run \
    --max_freq 5200
```

**Available scripts:**

| Script | `--plots` values | What it shows |
|---|---|---|
| `core_frequency_histogram.py` | `count`, `average` | Cores grouped by frequency band — every sample, then per-core averages |
| `each_core_frequency_histogram.py` | *(single plot)* | Frequency band distribution broken out per core, as grouped bars |
| `cores_active_histogram.py` | `average`, `active`, `p_and_e` | Cores grouped by average utilisation, by percentage of time active, and the P-core vs E-core split |
| `p_core_histograms.py` | `freq_count`, `freq_average`, `freq_each_core`, `average`, `active`, `p_and_e` | All six of the above for a P-cores-only run; PNGs are prefixed `p_core*` |
| `e_core_histograms.py` | same as above | The same set for an E-cores-only run; PNGs are prefixed `e_core*` |

Generate a subset by naming the plots you want:

```bash
python3 histograms/p_core_histograms.py <csv> --plots freq_average active
```

### P-cores and E-cores

The `p_and_e` plot compares performance cores against efficiency cores, which **only exist on Intel 12th gen and newer**. On older CPUs every core is the same kind of core, so there is nothing to compare — skip that plot via `--plots`.

On a hybrid CPU, which `core_<N>_*` column belongs to which class is hardware-specific and cannot be assumed from the column index. Check the layout with `lscpu -e` on the machine that produced the CSV, then pass the performance-core ids:

```bash
# defaults to 0-15, the i9-13900E layout; any id not listed counts as an E-core
python3 histograms/cores_active_histogram.py <csv> --plots p_and_e --p_cores 0-7,16-23
```

`--p_cores` accepts ranges (`0-15`), explicit ids (`0,1,2`), or a mix of both.