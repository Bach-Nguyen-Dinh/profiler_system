"""Per-core utilisation distribution from a profiler CSV -- the load-balance view.

One distribution per core, kept over time: for every core, how many of the run's
samples fell into each utilisation band. Two ways to draw it:

    grouped -- one bar group per core, one bar per band, y = sample count
    stacked -- one full-height bar per core, segments = share of the run spent
               in each band, with the core's mean annotated above it

This is deliberately not `cores_active_histogram.py --plots average`, which
averages each core down to a single number first and then bins those numbers,
so its whole output is a handful of bars saying how many cores were "busy on
average". Averaging hides the shape: a core sitting at a steady 50% and a core
that alternates between idle and pegged have the same mean and look identical
there, but land in completely different bands here.

Usage:
    python3 each_core_usage_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                         [--plots grouped stacked]
                                         [--bins 0,10,25,50,75,90,100]
                                         [--cores 0-7] [--cores-per-row 8] [--show]
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

# Cool for idle, hot for saturated, so a glance at the colours reads as load.
COLORMAP = 'YlOrRd'

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


def core_names(usage_columns):
    return [col.replace('_usage', '') for col in usage_columns]


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
# Grouped bars -- one group per core
#################################################################################################################################
def plot_grouped(df, output_dir, edges, cores, show, cores_per_row=DEFAULT_CORES_PER_ROW):
    usage_columns = core_usage_columns(df, cores)
    counts = band_counts(df, usage_columns, edges)
    labels = band_labels(edges)
    names = core_names(usage_columns)

    num_cores, num_bands = counts.shape
    bar_width = 0.8 / num_bands
    colors = plt.get_cmap(COLORMAP)(np.linspace(0.15, 0.9, num_bands))
    rows = core_rows(num_cores, cores_per_row)
    row_width = min(num_cores, cores_per_row)

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
    save(fig, output_dir, 'each_core_usage_histogram_grouped.png', show)


#################################################################################################################################
# Stacked shares -- one bar per core, normalised to the run length
#################################################################################################################################
def plot_stacked(df, output_dir, edges, cores, show, cores_per_row=DEFAULT_CORES_PER_ROW):
    usage_columns = core_usage_columns(df, cores)
    counts = band_counts(df, usage_columns, edges)
    labels = band_labels(edges)
    names = core_names(usage_columns)

    totals = counts.sum(axis=1, keepdims=True)
    shares = np.divide(counts, totals, out=np.zeros_like(counts, dtype=float),
                       where=totals > 0) * 100

    num_cores, num_bands = shares.shape
    colors = plt.get_cmap(COLORMAP)(np.linspace(0.15, 0.9, num_bands))
    means = df[usage_columns].mean()
    rows = core_rows(num_cores, cores_per_row)
    row_width = min(num_cores, cores_per_row)

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

        # The mean is what the averaging-based charts reduce each core to; showing
        # it on top makes it obvious how much the distribution below it is hiding.
        for xi, core in zip(x, row):
            ax.text(xi, 101, f"{means[usage_columns[core]]:.0f}%",
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
                 "(mean utilisation above each bar)")
    axes[-1].legend(title="Utilisation (%)", ncol=len(labels), fontsize=9,
                    loc='upper center', bbox_to_anchor=(0.5, -0.28))

    # tight_layout does not reserve room for a suptitle, so hold back a fixed
    # strip at the top -- a fraction, since the figure grows with the row count.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.45 / fig.get_figheight()))
    save(fig, output_dir, 'each_core_usage_histogram_stacked.png', show)


PLOTS = {
    'grouped': plot_grouped,
    'stacked': plot_stacked,
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
    parser.add_argument('--bins', default=','.join(f"{b:g}" for b in DEFAULT_BINS),
                        help="Comma-separated utilisation band edges "
                             f"(default: {','.join(f'{b:g}' for b in DEFAULT_BINS)})")
    parser.add_argument('--cores', default=None,
                        help="Restrict to these core ids, e.g. '0-15' or '0,1,2' "
                             "(default: every core in the CSV)")
    parser.add_argument('--cores-per-row', type=int, default=DEFAULT_CORES_PER_ROW,
                        help="Maximum cores drawn on one row; any beyond that spill onto "
                             f"further rows, each with its own axis (default: {DEFAULT_CORES_PER_ROW})")
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

    edges = parse_bins(args.bins)
    cores = parse_core_list(args.cores) if args.cores else None
    df = pd.read_csv(args.csv_path)

    if not core_usage_columns(df, cores):
        raise SystemExit("No core_<N>_usage columns found in the CSV "
                         "(or none matched --cores)")

    for name in args.plots:
        PLOTS[name](df, output_dir, edges, cores, args.show, args.cores_per_row)


if __name__ == '__main__':
    main()
