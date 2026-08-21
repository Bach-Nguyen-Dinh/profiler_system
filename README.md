# Profiler System

A Python-based system profiling tool that monitors CPU, memory, temperature, and power consumption during program execution.

## Setup

This project manages its own virtual environment with [uv](https://docs.astral.sh/uv/). If you don't have uv yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repo root:

```bash
uv sync
```

That creates `.venv/` with the exact dependency versions from `uv.lock`, downloading the pinned Python (3.11, see `.python-version`) if your system doesn't have it. You never need to activate the venv or run `pip install` — `uv run` picks it up automatically, and re-running `uv sync` after a `git pull` brings the environment back in step.

> **Note:** The venv is for the **profiler itself**. Your target script keeps running under your own `python3` with its own dependencies — see [Which interpreter runs your script](#which-interpreter-runs-your-script).

## Usage

Run the profiler by passing your target script as the first argument, followed by profiler options, then `--`, then any arguments for your target script:

```
uv run profiler_system/analyzer.py <target_script.py> [profiler options] -- [target script args]
```

**Profiler options:**
- `--metrics_interval_ms` — how often to sample metrics in milliseconds (default: 500)
- `--output_dir` — where to write output files (default: target script's directory)
- `--csv_write_interval_s` — how often to flush metrics to CSV in seconds (default: 5)
- `--target_python` — interpreter used to run the target script (default: `python3` from your `PATH`)

The `--` separator is required when passing arguments to the target script.

**Example:**

<!-- The "--" separates profiler parameters from target program parameters -->
```bash
uv run profiler_system/analyzer.py sar_colorization.py \
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

### Which interpreter runs your script

The profiler's venv holds only what the profiler needs (`psutil`, `matplotlib`, `networkx`, `pyvis`, `pandas`, `numpy`). Your target script is launched as a separate subprocess under plain `python3` — resolved from your `PATH`, *not* from the profiler's venv — so it keeps whatever environment it was written against. Nothing needs to be added to this project to profile a script that depends on torch, GDAL, or anything else.

This works because neither `uv run` nor the installed `profiler` wrapper activates the venv; they invoke `.venv/bin/python` directly, leaving `PATH` untouched.

To profile a script that lives in its own virtual environment, point at that interpreter explicitly:

```bash
uv run profiler_system/analyzer.py ~/my_project/train.py \
    --target_python ~/my_project/.venv/bin/python \
    -- --epochs 10
```

## Enabling CPU Power Metrics

CPU power measurement requires a one-time permission setup. If you see a warning like:

```
[Warning] CPU power metrics unavailable: permission denied.
```

Run the following command once:

```bash
sudo profiler_system/.venv/bin/python profiler_system/analyzer.py allow_cpu_power_metric_capture
```

(Or simply `sudo profiler allow_cpu_power_metric_capture` if you've installed the wrapper below.) The venv interpreter is named explicitly here because `sudo uv run` would look for `uv` on root's `PATH`, where it usually isn't.

After this, CPU power metrics will be collected automatically on all future runs without sudo. The setup persists across reboots.

> **Note:** This requires an Intel CPU with RAPL support. On unsupported hardware, power metrics will be silently skipped and all other metrics will still be collected.

## Installing system-wide (`profiler` command)

To run the profiler from anywhere without specifying the full path, use the provided install script. It writes a wrapper to `/usr/local/bin/profiler` that points to `analyzer.py` in this directory.

```bash
sudo bash install.sh
```

The script will:
1. Run `uv sync` to create or refresh `.venv/` from `uv.lock` (owned by your user, not root). If `uv` isn't installed, it stops and tells you how to get it.
2. Create `/usr/local/bin/profiler`, a wrapper that execs `.venv/bin/python analyzer.py`.

Because the wrapper names the venv interpreter directly, it works from any directory and doesn't touch your `PATH` — so profiled target scripts still run under your own `python3`.

After installing, you can use `profiler` instead of `uv run profiler_system/analyzer.py`:

```bash
profiler <target_script.py> [profiler options] -- [target script args]
sudo profiler allow_cpu_power_metric_capture
```

**Example:**

```bash
profiler /home/sarthak/workspace/SAR_codebase/cphd_aic.py --metrics_interval_ms 500 --csv_write_interval_s 5 -- --file /home/public/sar/sar-server/data/cphd/2023-10-22-15-20-28_CPHD.cphd 

```
  

> **Note:** The wrapper hard-codes the paths to this repo and its `.venv` at install time, so keep the repo in the same location after installing. If you move it, re-run `sudo bash install.sh` (a moved venv also needs `uv sync` to rebuild it, which the install script does for you).

### Uninstalling

```bash
sudo bash uninstall.sh
```

That removes `/usr/local/bin/profiler` and nothing else. It only deletes the wrapper if it actually points at this repo's `analyzer.py`, so a `profiler` command installed by something else is left alone (`--force` overrides that check).

The two other things the profiler may have put on your machine are opt-in flags, because neither is removed by uninstalling the command:

| Flag | Removes |
|---|---|
| `--venv` | this repo's `.venv/` — rebuild any time with `uv sync` |
| `--rapl` | `/etc/udev/rules.d/99-rapl.rules`, undoing `allow_cpu_power_metric_capture`, and reloads udev |
| `--all` | both of the above |

```bash
sudo bash uninstall.sh --all
```

> **Note:** `--rapl` stops the RAPL permissions from being reapplied on boot, but the currently-loaded permissions stay readable until you reboot.

## Histograms (`histograms/`)

The scripts in `histograms/` are standalone post-hoc analysis tools. They are not part of the profiling pipeline — run them afterwards against a CSV a profiling run already produced, to summarize how the cores were distributed across frequency and utilisation ranges.

Every script takes the CSV as its first argument:

```bash
uv run histograms/<script>.py <system_metrics_*.csv> [options]
```

**Options (all scripts):**
- `-o`, `--output_dir` — where to write the PNGs; they land in a `histogram/` subfolder of it (default: the directory the input CSV is in, i.e. the run's own `logs/<timestamp>/histogram/`)
- `--show` — display each plot interactively as well as saving it. Without this, plots are only written to disk.

Everything else is per script: `--plots` picks which histograms to generate (all but the two single-plot scripts take it — see the table below), `--max_freq` normalizes frequencies to a percentage, and the utilisation scripts take their own band and core-selection options — see [Utilisation scripts](#utilisation-scripts).

**Example:**

```bash
uv run histograms/core_frequency_histogram.py \
    logs/20260115_154219/system_metrics_20260115_154219.csv \
    --output_dir ~/analysis/january_run \
    --max_freq 5200
```

**Available scripts:**

*Frequency, and cores reduced to one number each:*

| Script | `--plots` values | What it shows |
|---|---|---|
| `core_frequency_histogram.py` | `count`, `average` | Cores grouped by frequency band — every sample, then per-core averages |
| `each_core_frequency_histogram.py` | *(single plot)* | Frequency band distribution broken out per core, as grouped bars |
| `cores_active_histogram.py` | `average`, `active`, `p_and_e` | Cores grouped by average utilisation, by percentage of time active, and the P-core vs E-core split |
| `p_core_histograms.py` | `freq_count`, `freq_average`, `freq_each_core`, `average`, `active`, `p_and_e` | All six of the above for a P-cores-only run; PNGs are prefixed `p_core*` |
| `e_core_histograms.py` | same as above | The same set for an E-cores-only run; PNGs are prefixed `e_core*` |

*Utilisation, keeping every sample:*

| Script | `--plots` values | What it shows |
|---|---|---|
| `core_usage_histogram.py` | `grouped`, `stacked`, `cores`, `active`, `p_and_e` | The whole utilisation picture in one script: per-core distributions (`grouped`, `stacked`) alongside the core-count summaries (`cores`, `active`, `p_and_e`) |
| `each_core_usage_histogram.py` | `grouped`, `stacked` | Just the per-core distributions — the `grouped`/`stacked` half of the above, on its own |
| `pooled_core_usage_histogram.py` | *(single plot)* | Every core reading from every sample thrown into one pool and binned — the overall shape of the load |

Generate a subset by naming the plots you want:

```bash
uv run histograms/p_core_histograms.py <csv> --plots freq_average active
```

### Utilisation scripts

`cores_active_histogram.py --plots average` averages each core down to a single number and then bins those numbers, so its entire output is a handful of bars saying how many cores were busy on average. That hides the shape of the load: a core sitting at a steady 50% and a core alternating between idle and pegged have the same mean, and are indistinguishable there.

The three utilisation scripts keep every sample instead. `core_usage_histogram.py` is the one to reach for — it covers both views, and the other two are narrower cuts of the same data:

- **`grouped` / `stacked`** — one distribution per core. `grouped` draws a bar per band per core (y = sample count); `stacked` draws one full-height bar per core, segmented by the share of the run spent in each band, with the core's summary stat annotated above it.
- **`cores` / `active` / `p_and_e`** — the fleet-level counts, as in `cores_active_histogram.py`.
- **`pooled_core_usage_histogram.py`** — one histogram of all `core_<N>_usage` readings pooled together (n = cores × samples), so the distribution has a usable shape even on a short run. A bimodal result — a pile near 0% and a spike at 100% — means the work is arriving as a few pegged threads rather than spreading across the cores.

**Extra options:**

| Option | Scripts | Meaning |
|---|---|---|
| `--bins` | `core_usage`, `each_core_usage` | Comma-separated band edges (default: `0,10,25,50,75,90,100` — deliberately uneven, since the interesting structure is at the idle and saturated ends) |
| `--stat mean\|median` | `core_usage` | How to reduce a core to one number for the `cores`, `p_and_e` and stacked-annotation charts (default: `mean`) |
| `--cores` | all three | Restrict to these core ids, e.g. `0-15` or `0,1,2` (default: every core in the CSV) |
| `--cores-per-row` | `core_usage`, `each_core_usage` | Cores per row of the `grouped`/`stacked` charts; the rest spill onto further rows (default: 8) |
| `--bin_width` | `pooled_core_usage` | Bin width in utilisation percent (default: 5) |
| `--split_saturated` | `pooled_core_usage` | Give the clipped 100% readings their own bar instead of folding them into the top bin |
| `--p_cores` | `core_usage` | P-core ids for the `p_and_e` plot — see [P-cores and E-cores](#p-cores-and-e-cores) |

A mean is dragged upward by a handful of saturated samples, so a core that idles through most of a run but spikes hard is reported as busy on average; the median says what the core was doing for most of the run. Comparing the two is the cheapest way to spot cores whose load is spiky rather than steady — the outputs are named after the stat, so neither run overwrites the other:

```bash
uv run histograms/core_usage_histogram.py <csv> --plots cores stacked --stat mean
uv run histograms/core_usage_histogram.py <csv> --plots cores stacked --stat median
```

On a hybrid CPU, pooling P-cores and E-cores separately is usually more informative than pooling them together:

```bash
uv run histograms/pooled_core_usage_histogram.py <csv> --cores 0-15 --split_saturated
```

### P-cores and E-cores

The `p_and_e` plot compares performance cores against efficiency cores, which **only exist on Intel 12th gen and newer**. On older CPUs every core is the same kind of core, so there is nothing to compare — skip that plot via `--plots`.

On a hybrid CPU, which `core_<N>_*` column belongs to which class is hardware-specific and cannot be assumed from the column index. Check the layout with `lscpu -e` on the machine that produced the CSV, then pass the performance-core ids:

```bash
# defaults to 0-15, the i9-13900E layout; any id not listed counts as an E-core
uv run histograms/cores_active_histogram.py <csv> --plots p_and_e --p_cores 0-7,16-23
```

`--p_cores` accepts ranges (`0-15`), explicit ids (`0,1,2`), or a mix of both.