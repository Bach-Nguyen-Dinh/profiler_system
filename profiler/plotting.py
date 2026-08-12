"""Charting of a metrics CSV.

Writes six standalone PNGs plus one combined dashboard, all sharing the run's
timestamp so they file together. Each panel is drawn by one function that is
called twice -- once onto the dashboard grid, once onto its own figure -- so the
two never drift apart.

A metric with no samples is drawn as an explicit "not available" panel instead
of an empty set of axes, and the panel says *which* kind of absence it is --
a source this machine never had, or one that stopped reporting mid-run. For
power the first case cannot happen: it is required, so the run aborts up front.
For temperature it happens routinely, on any machine whose firmware declares no
ACPI thermal zone.

The temperature panel has a third state worth knowing about: a zone that
reports a constant. That draws a normal-looking flat line, so when the run
flagged it the panel is captioned to say the variation is not measured.
"""
import json
import os
import re
from datetime import datetime

import matplotlib

matplotlib.use("Agg")   # never try to open a window; we only ever savefig

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

_STAMP = re.compile(r"_(\d{8}_\d{6})\.csv$", re.IGNORECASE)


def _log_step(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def _run_timestamp(path):
    match = _STAMP.search(os.path.basename(path))
    if not match:
        raise ValueError(
            f"cannot recover the run timestamp from {os.path.basename(path)}; "
            "metrics CSVs must be named system_metrics_YYYYmmdd_HHMMSS.csv")
    return match.group(1)


def _load_metadata(csv_path):
    """Read the JSON sidecar written next to the CSV, if it exists."""
    sidecar = os.path.splitext(csv_path)[0] + ".json"
    try:
        with open(sidecar) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _core_labels(columns, meta):
    """Label per-core series, using P/E names only on a genuinely hybrid CPU."""
    core_class = meta.get("core_class") or {}
    hybrid = meta.get("hybrid_cpu") and core_class
    labels = {}
    for col in columns:
        index = col.split("_")[1]
        if hybrid and core_class.get(index):
            labels[col] = f"{core_class[index]}-core {index}"
        else:
            labels[col] = f"Core {index}"
    return labels


def _unavailable(ax, title, reason):
    ax.set_title(title)
    ax.text(0.5, 0.5, reason, ha="center", va="center", fontsize=11,
            color="grey", wrap=True, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    # Tell _finish to leave this panel bare rather than re-adding axes furniture.
    ax._profiler_blank = True


def _has_data(df, column):
    return column in df.columns and df[column].notna().any()


# ------------------------------------------------------------------- panels
def _panel_memory(ax, ctx):
    df = ctx["df"]
    gb = df["memory_usage"].values * df["total_memory"].values / 100 / (1024 ** 3)
    ax.plot(df["RelativeTime"].values, gb, "b-", linewidth=2, label="Memory usage")
    ax.set_title("Memory usage over time")
    ax.set_ylabel("Memory usage (GB)")
    ax.legend()


def _panel_core_usage(ax, ctx):
    df, labels = ctx["df"], ctx["usage_labels"]
    columns = ctx["usage_columns"]
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(columns), 1)))
    for i, col in enumerate(columns):
        ax.plot(df["RelativeTime"].values, df[col].values, color=colors[i],
                linewidth=1.5, label=labels[col], alpha=0.8)
    ax.set_title("CPU cores usage over time")
    ax.set_ylabel("CPU usage (%)")
    ax.set_ylim(-5, 105)
    ax.set_yticks(range(0, 101, 20))
    ax.legend(bbox_to_anchor=(1.02, 0.5), loc="center left", fontsize=9)


def _panel_core_frequency(ax, ctx):
    df, labels = ctx["df"], ctx["freq_labels"]
    columns = [c for c in ctx["freq_columns"] if df[c].notna().any()]
    if not columns:
        _unavailable(ax, "CPU cores frequency over time",
                     "per-core frequency unavailable\n"
                     "(PDH processor performance counters could not be read)")
        return
    colors = plt.cm.tab10(np.linspace(0, 1, len(columns)))
    for i, col in enumerate(columns):
        ax.plot(df["RelativeTime"].values, df[col].values, color=colors[i],
                linewidth=1.5, label=labels[col], alpha=0.8)
    ax.set_title("CPU cores frequency over time")
    ax.set_ylabel("Frequency (MHz)")
    ax.legend(bbox_to_anchor=(1.02, 0.5), loc="center left", fontsize=9)


def _panel_power(ax, ctx):
    df = ctx["df"]
    if not _has_data(df, "cpu_power"):
        _unavailable(ax, "CPU power consumption over time",
                     "no CPU power samples in this run\n"
                     "Power is a required metric, so its source was\n"
                     "present at start and stopped reporting since.\n"
                     "Run `profiler diagnose` to see what this machine offers.")
        return
    ax.plot(df["RelativeTime"].values, df["cpu_power"].values, "r-",
            linewidth=2, label="CPU power")
    ax.set_title("CPU power consumption over time")
    ax.set_ylabel("Power (W)")
    ax.legend()


def _panel_temperature(ax, ctx):
    df, meta = ctx["df"], ctx["meta"]
    if not _has_data(df, "cpu_temperature"):
        # Two different situations, and saying "sensor lost" for the first one
        # would send the reader looking for a fault that is not there.
        if meta.get("temperature_available") is False:
            reason = ("no CPU temperature on this machine\n\n"
                      "Its firmware declares no readable ACPI thermal zone,\n"
                      "and Windows exposes no on-die CPU sensor to user mode.\n"
                      "Nothing is wrong with the run: every other metric,\n"
                      "power included, was sampled normally.")
        else:
            reason = ("no CPU temperature samples in this run\n\n"
                      "The thermal zone answered at start and stopped\n"
                      "reporting part-way through.\n"
                      "Run `profiler diagnose` to see what this machine offers.")
        _unavailable(ax, "CPU temperature over time", reason)
        return
    ax.plot(df["RelativeTime"].values, df["cpu_temperature"].values, "orange",
            linewidth=2, label="CPU temperature")
    ax.set_title("CPU temperature over time")
    ax.set_ylabel("Temperature (°C)")
    ax.legend()

    if not ctx["meta"].get("temperature_static"):
        return
    # The run established that this zone never moved while load swung. A flat
    # line drawn on auto-scaled axes looks like a measurement; say plainly that
    # it is not, on the chart itself, because the PNG travels without the log.
    value = df["cpu_temperature"].iloc[0]
    ax.set_ylim(value - 10, value + 10)
    ax.text(0.5, 0.88,
            "This machine's ACPI thermal zone reports a constant.\n"
            "The reading is real; the variation is not measured.\n"
            "Windows exposes no on-die CPU sensor to user mode.",
            transform=ax.transAxes, ha="center", va="top", fontsize=10,
            color="#8a1c1c",
            bbox={"boxstyle": "round", "facecolor": "#ffe9e9",
                  "edgecolor": "#8a1c1c", "alpha": 0.95})


def _panel_overall_cpu(ax, ctx):
    df = ctx["df"]
    ax.plot(df["RelativeTime"].values, df["cpu_usage"].values, "g-",
            linewidth=2, label="Overall CPU usage")
    ax.set_title("Overall CPU usage over time")
    ax.set_ylabel("CPU usage (%)")
    ax.set_ylim(-5, 105)
    ax.set_yticks(range(0, 101, 20))
    ax.legend()


PANELS = [
    ("memory_usage", _panel_memory),
    ("cpu_cores_usage", _panel_core_usage),
    ("cpu_cores_frequency", _panel_core_frequency),
    ("cpu_power", _panel_power),
    ("cpu_temperature", _panel_temperature),
    ("overall_cpu_usage", _panel_overall_cpu),
]


def _finish(ax, ctx):
    if getattr(ax, "_profiler_blank", False):
        return
    ax.set_xlabel(ctx["time_label"])
    ax.grid(True, alpha=0.7)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=ctx["nbins"]))


# --------------------------------------------------------------------- entry
def plot_system_metrics(input_filename, output_dir="."):
    _log_step("Plotting the logs")
    timestamp = _run_timestamp(input_filename)
    meta = _load_metadata(input_filename)

    df = pd.read_csv(input_filename)
    if df.empty:
        print("Metrics CSV is empty; nothing to plot.")
        return []

    df["Timestamp"] = pd.to_datetime(df["Timestamp"])

    # Negative readings are sampling glitches; carry the previous value forward.
    for col in df.select_dtypes(include=[np.number]).columns:
        df[col] = df[col].mask(df[col] < 0).ffill()

    df["RelativeTime"] = (df["Timestamp"] - df["Timestamp"].iloc[0]).dt.total_seconds()
    span = df["RelativeTime"].max() - df["RelativeTime"].min()
    print(f"Time span: {span:.1f} seconds ({span / 60:.1f} minutes)")

    if span >= 3600:
        df["RelativeTime"] = df["RelativeTime"] / 3600
        time_label = "Time (h)"
        _log_step(f"Time axis in hours ({span / 3600:.1f} hours)")
    else:
        time_label = "Time (s)"
        _log_step("Time axis in seconds")

    nbins = 10 if span <= 60 else 8 if span <= 300 else 6 if span <= 3600 else 5

    usage_columns = [c for c in df.columns
                     if c.startswith("core_") and c.endswith("_usage")]
    freq_columns = [c for c in df.columns
                    if c.startswith("core_") and c.endswith("_frequency")]

    ctx = {
        "df": df,
        "meta": meta,
        "time_label": time_label,
        "nbins": nbins,
        "usage_columns": usage_columns,
        "freq_columns": freq_columns,
        "usage_labels": _core_labels(usage_columns, meta),
        "freq_labels": _core_labels(freq_columns, meta),
    }

    written = []
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    for (name, draw), ax in zip(PANELS, axes.flat):
        draw(ax, ctx)
        _finish(ax, ctx)

        solo = plt.figure(figsize=(14, 8))
        solo_ax = solo.add_subplot(111)
        draw(solo_ax, ctx)
        _finish(solo_ax, ctx)
        path = os.path.join(output_dir, f"{name}_{timestamp}.png")
        solo.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(solo)
        written.append(path)
        _log_step(f"Plotted {name}")

    fig.tight_layout()
    dashboard = os.path.join(output_dir, f"system_metrics_dashboard_{timestamp}.png")
    fig.savefig(dashboard, dpi=300, bbox_inches="tight")
    plt.close(fig)
    written.append(dashboard)
    _log_step("Plotted dashboard")

    return written
