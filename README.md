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