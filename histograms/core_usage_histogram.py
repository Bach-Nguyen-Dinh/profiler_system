"""Core-utilisation histograms from a profiler CSV -- the per-core distributions
and the core-count summaries in one place.

Two families of chart, both fed by the same `core_<N>_usage` columns and the
same utilisation bands:

    grouped -- one bar group per core, one bar per band, y = sample count
    stacked -- one full-height bar per core, segments = share of the run spent
               in each band, with the core's summary stat annotated above it
    cores   -- how many cores had a summary utilisation in each band
    active  -- how many cores were active (>0%) for each share of the run
    p_and_e -- the summary-utilisation bands split into P-cores and E-cores

The first two keep every sample, so the shape of a core's load is visible: a
core sitting at a steady 50% and a core alternating between idle and pegged
look completely different there. The last three reduce each core to a single
number first and count cores, which is the fleet-level view -- how many cores
are carrying the work at all.

Which single number that is, is up to `--stat`. The mean (the default) is
dragged upward by a handful of saturated samples, so a core that idles through
most of the run but spikes hard is reported as "busy on average"; the median
says instead what the core was doing for most of the run. Running both and
comparing them is the cheapest way to spot cores whose load is spiky rather
than steady -- the outputs are named after the stat, so neither run overwrites
the other.

Usage:
    python3 core_usage_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                    [--plots grouped stacked cores active p_and_e]
                                    [--stat mean|median]
                                    [--bins 0,10,25,50,75,90,100]
                                    [--cores 0-7] [--cores-per-row 8]
                                    [--p_cores 0-15] [--show]

The `p_and_e` plot only makes sense on a hybrid CPU (Intel 12th gen and newer).
Which core_<N>_* column belongs to which class is hardware-specific -- check
`lscpu -e` on the machine that produced the CSV and pass --p_cores accordingly.
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

# Deliberately uneven: the interesting structure is at the two ends (idle and
# saturated), so the middle of the range gets coarser bands.
DEFAULT_BINS = [0, 10, 25, 50, 75, 90, 100]

# Active time is a different quantity from utilisation -- a core is either
# doing something or it is not -- so it gets its own bands, packed up near
# 100% where the differences between cores actually show up.
ACTIVE_BINS = [0, 70, 80, 90, 100]

# Cool for idle, hot for saturated, so a glance at the colours reads as load.
COLORMAP = 'YlOrRd'

# The core-count charts are one bar per band rather than a gradient of load,
# so they keep the flat fill the older histograms used.
COUNT_COLOR = 'skyblue'
E_CORE_COLOR = 'orange'

# Past this many cores the bars get too thin to read, so the cores are split
# over several stacked rows, each with its own axis, instead of one long strip.
DEFAULT_CORES_PER_ROW = 8


def core_usage_columns(df, cores=None):
    """Per-core usage columns, by the `core_<N>_usage` naming convention.

    If `cores` is given, only the columns for those core ids are returned.
    """
    columns = [col for col in df.columns
               if col.startswith('core_') and col.endswith('_usage')]
    if cores is not None:
        columns = [col for col in columns if int(col.split('_')[1]) in cores]
    return columns


def core_ids(usage_columns):
    return [int(col.split('_')[1]) for col in usage_columns]


def core_names(usage_columns):
    return [col.replace('_usage', '') for col in usage_columns]


def band_labels(edges):
    labels = [f"<{edges[1]:g}"]
    labels += [f"{lo:g}-{hi:g}" for lo, hi in zip(edges[1:-2], edges[2:-1])]
    labels.append(f">{edges[-2]:g}")
    return labels


def band_counts(df, usage_columns, edges):
    """Matrix of per-core sample counts per band, shape (cores, bands)."""
    counts = []
    for col in usage_columns:
        values = df[col].to_numpy(dtype=float)
        values = values[~np.isnan(values)]
        # np.histogram closes the final bin on the right, so 100.0 is counted.
        per_band, _ = np.histogram(values, bins=edges)
        counts.append(per_band)
    return np.array(counts)


def core_stat(df, usage_columns, stat):
    """One number per core: its mean or its median utilisation over the run."""
    return getattr(df[usage_columns], stat)()


def counts_per_band(values, edges):
    """How many of `values` fall into each band -- one number per band.

    Used to bin cores by a single per-core statistic (median utilisation,
    share of the run spent active), as opposed to binning raw samples.
    """
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    per_band, _ = np.histogram(values, bins=edges)
    return per_band


def save(fig, output_dir, filename, show):
    out_path = os.path.join(output_dir, filename)
    fig.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Wrote {out_path}")
    if show:
        plt.show()
    plt.close(fig)


def integer_ticks(axis):
    """Counts are whole numbers -- keep the tick marks off values like 2.5."""
    axis.set_major_locator(MaxNLocator(integer=True))


def core_rows(num_cores, per_row):
    """Core indices split into rows of at most `per_row` cores each."""
    return [np.arange(start, min(start + per_row, num_cores))
            for start in range(0, num_cores, per_row)]


#################################################################################################################################
# Grouped bars -- one group per core, every sample kept
#################################################################################################################################
def plot_grouped(df, output_dir, opts):
    usage_columns = core_usage_columns(df, opts.cores)
    counts = band_counts(df, usage_columns, opts.edges)
    labels = band_labels(opts.edges)
    names = core_names(usage_columns)

    num_cores, num_bands = counts.shape
    bar_width = 0.8 / num_bands
    colors = plt.get_cmap(COLORMAP)(np.linspace(0.15, 0.9, num_bands))
    rows = core_rows(num_cores, opts.cores_per_row)
    row_width = min(num_cores, opts.cores_per_row)

    fig, axes = plt.subplots(len(rows), 1, squeeze=False,
                             figsize=(max(10, row_width * 1.4), 5 * len(rows)))
    axes = axes[:, 0]
    for ax, row in zip(axes, rows):
        x = np.arange(len(row))
        for i in range(num_bands):
            ax.bar(x + i * bar_width, counts[row, i], width=bar_width,
                   color=colors[i], edgecolor='black', linewidth=0.3, label=labels[i])
        ax.set_ylabel("Number of samples")
        integer_ticks(ax.yaxis)
        ax.set_xticks(x + bar_width * (num_bands - 1) / 2)
        ax.set_xticklabels([names[i] for i in row], rotation=90)
        # Same x and y span on every row, so a partial last row keeps the bar
        # width of the full rows and the heights stay comparable between rows.
        ax.set_xlim(-0.5, row_width - 0.5 + bar_width * num_bands)
        ax.set_ylim(0, max(counts.max() * 1.05, 1))
        ax.grid(axis='y', alpha=0.3)

    axes[-1].set_xlabel("CPU core")
    fig.suptitle(f"Per-Core Utilisation Distribution ({len(df)} samples per core)")
    axes[-1].legend(title="Utilisation (%)", ncol=len(labels), fontsize=9,
                    loc='upper center', bbox_to_anchor=(0.5, -0.28))

    # tight_layout does not reserve room for a suptitle, so hold back a fixed
    # strip at the top -- a fraction, since the figure grows with the row count.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.45 / fig.get_figheight()))
    save(fig, output_dir, 'core_usage_histogram_grouped.png', opts.show)


#################################################################################################################################
# Stacked shares -- one bar per core, normalised to the run length
#################################################################################################################################
def plot_stacked(df, output_dir, opts):
    usage_columns = core_usage_columns(df, opts.cores)
    counts = band_counts(df, usage_columns, opts.edges)
    labels = band_labels(opts.edges)
    names = core_names(usage_columns)

    totals = counts.sum(axis=1, keepdims=True)
    shares = np.divide(counts, totals, out=np.zeros_like(counts, dtype=float),
                       where=totals > 0) * 100

    num_cores, num_bands = shares.shape
    colors = plt.get_cmap(COLORMAP)(np.linspace(0.15, 0.9, num_bands))
    stats = core_stat(df, usage_columns, opts.stat)
    rows = core_rows(num_cores, opts.cores_per_row)
    row_width = min(num_cores, opts.cores_per_row)

    fig, axes = plt.subplots(len(rows), 1, squeeze=False,
                             figsize=(max(10, row_width * 1.1), 5 * len(rows)))
    axes = axes[:, 0]
    for ax, row in zip(axes, rows):
        x = np.arange(len(row))
        bottom = np.zeros(len(row))
        for i in range(num_bands):
            ax.bar(x, shares[row, i], bottom=bottom, width=0.7, color=colors[i],
                   edgecolor='black', linewidth=0.3, label=labels[i])
            bottom += shares[row, i]

        # This is what the core-count charts reduce each core to; showing it on
        # top makes it obvious how much the distribution below it is hiding.
        for xi, core in zip(x, row):
            ax.text(xi, 101, f"{stats[usage_columns[core]]:.0f}%",
                    ha='center', va='bottom', fontsize=8)

        ax.set_ylabel("Share of samples (%)")
        ax.set_xticks(x)
        ax.set_xticklabels([names[i] for i in row], rotation=90)
        # A partial last row keeps the bar width of the full rows above it.
        ax.set_xlim(-0.5, row_width - 0.5)
        ax.set_ylim(0, 108)
        ax.grid(axis='y', alpha=0.3)

    axes[-1].set_xlabel("CPU core")
    fig.suptitle("Per-Core Time Spent in Each Utilisation Band "
                 f"({opts.stat} utilisation above each bar)")
    axes[-1].legend(title="Utilisation (%)", ncol=len(labels), fontsize=9,
                    loc='upper center', bbox_to_anchor=(0.5, -0.28))

    # tight_layout does not reserve room for a suptitle, so hold back a fixed
    # strip at the top -- a fraction, since the figure grows with the row count.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.45 / fig.get_figheight()))
    save(fig, output_dir, f'core_usage_histogram_stacked_{opts.stat}.png', opts.show)


#################################################################################################################################
# Summary utilisation -- how many cores sat in each band
#################################################################################################################################
def plot_core_counts(df, output_dir, opts):
    usage_columns = core_usage_columns(df, opts.cores)
    labels = band_labels(opts.edges)
    counts = counts_per_band(core_stat(df, usage_columns, opts.stat), opts.edges)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, counts, color=COUNT_COLOR, edgecolor='black')
    ax.set_title(f"Number of Cores Per {opts.stat.capitalize()} Usage Range")
    ax.set_xlabel(f"{opts.stat.capitalize()} CPU Usage Range (%)")
    ax.set_ylabel("Number of CPU Cores")
    integer_ticks(ax.yaxis)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    fig.tight_layout()
    save(fig, output_dir, f'core_usage_histogram_{opts.stat}.png', opts.show)


#################################################################################################################################
# Active time -- how much of the run each core spent doing anything at all
#################################################################################################################################
def plot_active_time(df, output_dir, opts):
    usage_columns = core_usage_columns(df, opts.cores)
    labels = band_labels(ACTIVE_BINS)

    # Percentage of samples in which the core was doing any work at all.
    core_active_pct = ((df[usage_columns] > 0).sum() / len(df)) * 100
    counts = counts_per_band(core_active_pct, ACTIVE_BINS)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, counts, color=COUNT_COLOR, edgecolor='black')
    ax.set_title("Number of Cores Per Active-Time Range")
    ax.set_xlabel("Percentage of Time Core is Active")
    ax.set_ylabel("Number of CPU Cores")
    integer_ticks(ax.yaxis)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    fig.tight_layout()
    save(fig, output_dir, 'core_usage_histogram_active.png', opts.show)


#################################################################################################################################
# Summary utilisation -- Performance vs Efficiency cores
#################################################################################################################################
def plot_p_and_e_usage(df, output_dir, opts):
    usage_columns = core_usage_columns(df, opts.cores)
    labels = band_labels(opts.edges)

    p_columns = [col for col, cid in zip(usage_columns, core_ids(usage_columns))
                 if cid in opts.p_cores]
    e_columns = [col for col in usage_columns if col not in p_columns]

    p_counts = counts_per_band(core_stat(df, p_columns, opts.stat), opts.edges)
    e_counts = counts_per_band(core_stat(df, e_columns, opts.stat), opts.edges)

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, p_counts, width, color=COUNT_COLOR,
           edgecolor='black', label='P-cores')
    ax.bar(x + width / 2, e_counts, width, color=E_CORE_COLOR,
           edgecolor='black', label='E-cores')

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title("Core Usage Distribution (P-cores vs E-cores)")
    ax.set_xlabel(f"{opts.stat.capitalize()} CPU Core Usage (%)")
    ax.set_ylabel("Number of Cores")
    integer_ticks(ax.yaxis)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    ax.legend()
    fig.tight_layout()
    save(fig, output_dir, f'core_usage_histogram_p_and_e_{opts.stat}.png', opts.show)


PLOTS = {
    'grouped': plot_grouped,
    'stacked': plot_stacked,
    'cores': plot_core_counts,
    'active': plot_active_time,
    'p_and_e': plot_p_and_e_usage,
}


def parse_core_list(spec):
    """Parse a core-id spec like "0-15" or "0,1,2" or "0-7,16-23" into a set of ints."""
    cores = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            cores.update(range(int(start), int(end) + 1))
        else:
            cores.add(int(part))
    return cores


def parse_bins(spec):
    edges = [float(part) for part in spec.split(',') if part.strip()]
    if len(edges) < 3:
        raise SystemExit("--bins needs at least three edges, e.g. '0,50,100'")
    if any(b <= a for a, b in zip(edges, edges[1:])):
        raise SystemExit("--bins must be strictly increasing")
    return edges


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv_path',
                        help="Path to a system_metrics_<timestamp>.csv produced by the profiler")
    parser.add_argument('-o', '--output_dir', default=None,
                        help="Directory to write the PNGs into, under a histogram/ subfolder of it "
                             "(default: the directory the input CSV is in)")
    parser.add_argument('--plots', nargs='+', choices=sorted(PLOTS), default=sorted(PLOTS),
                        help="Which charts to generate (default: all)")
    parser.add_argument('--stat', choices=('mean', 'median'), default='mean',
                        help="How to reduce each core to one number for the cores, p_and_e and "
                             "stacked-annotation charts: 'mean' counts every saturated sample in "
                             "full, 'median' resists them (default: mean)")
    parser.add_argument('--bins', default=','.join(f"{b:g}" for b in DEFAULT_BINS),
                        help="Comma-separated utilisation band edges, used both for the per-core "
                             "distributions and for grouping cores by median utilisation "
                             f"(default: {','.join(f'{b:g}' for b in DEFAULT_BINS)})")
    parser.add_argument('--cores', default=None,
                        help="Restrict to these core ids, e.g. '0-15' or '0,1,2' "
                             "(default: every core in the CSV)")
    parser.add_argument('--cores-per-row', type=int, default=DEFAULT_CORES_PER_ROW,
                        help="Maximum cores drawn on one row of the grouped and stacked charts; "
                             "any beyond that spill onto further rows, each with its own axis "
                             f"(default: {DEFAULT_CORES_PER_ROW})")
    parser.add_argument('--p_cores', default='0-15',
                        help="P-core column ids for the p_and_e plot, e.g. '0-15' or '0,1,2' "
                             "(default: 0-15, the i9-13900E layout; all other ids count as E-cores)")
    parser.add_argument('--show', action='store_true',
                        help="Display each plot interactively in addition to saving it")
    return parser.parse_args()


def main():
    args = parse_args()
    # The graphs go into a histogram/ subfolder of the output directory --
    # by default the run's own directory, next to the CSV they came from --
    # so they sit apart from the profiler's own PNGs and CSV.
    output_dir = os.path.join(
        args.output_dir or os.path.dirname(os.path.abspath(args.csv_path)), 'histogram')
    os.makedirs(output_dir, exist_ok=True)

    if args.cores_per_row < 1:
        raise SystemExit("--cores-per-row must be at least 1")

    args.edges = parse_bins(args.bins)
    args.cores = parse_core_list(args.cores) if args.cores else None
    args.p_cores = parse_core_list(args.p_cores)
    df = pd.read_csv(args.csv_path)

    if not core_usage_columns(df, args.cores):
        raise SystemExit("No core_<N>_usage columns found in the CSV "
                         "(or none matched --cores)")

    for name in args.plots:
        # Every plot takes the parsed options whole, so they can share one loop
        # despite needing different subsets of them.
        PLOTS[name](df, output_dir, args)


if __name__ == '__main__':
    main()
