"""Pooled per-core utilisation histogram from a profiler CSV.

Every `core_<N>_usage` reading from every sample is thrown into one pool
(n = cores x samples) and binned, so the shape of the distribution is visible
even on short runs where a histogram of the aggregate `cpu_usage` column would
only have one point per sample.

A bimodal result -- a pile near 0% and a spike at 100% with little in between --
means cores are either idle or saturated, i.e. the work arrives as a few
pegged threads rather than being spread across the cores.

100.0 is a clipping value rather than an ordinary measurement, so the top bin
counts it together with the readings just below it. Pass --split_saturated to
give those clipped readings a bar of their own; either way the summary box
reports what share of the pool they are.

Usage:
    python3 pooled_core_usage_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                           [--bin_width 5] [--cores 0-7]
                                           [--split_saturated] [--show]
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

# A psutil percentage of 100.0 is the clipped top of the scale; anything this
# close to it is treated as saturated rather than as a reading inside the range.
SATURATION_EPS = 0.05


def integer_ticks(axis):
    """Counts are whole numbers -- keep the tick marks off values like 2.5."""
    axis.set_major_locator(MaxNLocator(integer=True))


def core_usage_columns(df, cores=None):
    """Per-core usage columns, by the `core_<N>_usage` naming convention.

    If `cores` is given, only the columns for those core ids are returned.
    """
    columns = [col for col in df.columns
               if col.startswith('core_') and col.endswith('_usage')]
    if cores is not None:
        columns = [col for col in columns if int(col.split('_')[1]) in cores]
    return columns


def usage_bin_edges(bin_width):
    """Edges from 0 to 100 in steps of `bin_width`, with the last bin truncated
    at 100 if the width does not divide evenly."""
    edges = np.arange(0, 100, bin_width, dtype=float)
    return np.append(edges, 100.0)


def plot_pooled_core_usage(df, output_dir, bin_width, cores, split_saturated, show,
                           filename='pooled_core_usage_histogram.png'):
    usage_columns = core_usage_columns(df, cores)
    if not usage_columns:
        raise SystemExit("No core_<N>_usage columns found in the CSV "
                         "(or none matched --cores)")

    values = df[usage_columns].to_numpy(dtype=float).ravel()
    values = values[~np.isnan(values)]
    if values.size == 0:
        raise SystemExit("No usable core utilisation readings in the CSV")

    saturated = values >= 100.0 - SATURATION_EPS
    binned = values[~saturated] if split_saturated else values

    edges = usage_bin_edges(bin_width)
    counts, _ = np.histogram(binned, bins=edges)
    labels = [f"{lo:g}-{hi:g}" for lo, hi in zip(edges[:-1], edges[1:])]

    # Optionally lift the saturation spike out of the top bin, as its own bar
    # past the end of the range.
    colors = ['tab:blue'] * len(counts)
    if split_saturated:
        counts = np.append(counts, saturated.sum())
        labels.append('=100')
        colors.append('tab:orange')

    total = values.size
    x = np.arange(len(counts))

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x, counts, width=0.85, color=colors, edgecolor='black', linewidth=0.4)

    ax.set_xlabel("Core utilisation (%)")
    ax.set_ylabel("Number of samples")
    integer_ticks(ax.yaxis)
    ax.set_title(f"Pooled Core Utilisation Distribution "
                 f"({len(usage_columns)} cores x {len(df)} samples, n={total})")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=90)
    ax.grid(axis='y', alpha=0.3)

    # Second y axis reading the same bars as a share of all core-samples.
    percent_axis = ax.secondary_yaxis(
        'right', functions=(lambda c: c / total * 100, lambda p: p / 100 * total))
    percent_axis.set_ylabel("Share of samples (%)")

    summary = (f"mean {values.mean():.1f}%   median {np.median(values):.1f}%\n"
               f"< 10%: {(values < 10).mean() * 100:.1f}% of samples\n"
               f"saturated (100%): {saturated.mean() * 100:.1f}% of samples")
    ax.text(0.98, 0.97, summary, transform=ax.transAxes, ha='right', va='top',
            fontsize=9, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    fig.tight_layout()

    out_path = os.path.join(output_dir, filename)
    fig.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Wrote {out_path}")
    if show:
        plt.show()
    plt.close(fig)


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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv_path',
                        help="Path to a system_metrics_<timestamp>.csv produced by the profiler")
    parser.add_argument('-o', '--output_dir', default=None,
                        help="Directory to write the PNG into, under a histogram/ subfolder of it "
                             "(default: the directory the input CSV is in)")
    parser.add_argument('--bin_width', type=float, default=5,
                        help="Histogram bin width in utilisation percent (default: 5)")
    parser.add_argument('--cores', default=None,
                        help="Restrict the pool to these core ids, e.g. '0-15' or '0,1,2' "
                             "(default: every core in the CSV). Useful on a hybrid CPU to pool "
                             "P-cores and E-cores separately.")
    parser.add_argument('--split_saturated', action='store_true',
                        help="Lift the 100%% readings out of the top bin and give them their "
                             "own bar")
    parser.add_argument('--show', action='store_true',
                        help="Display the plot interactively in addition to saving it")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.bin_width <= 0 or args.bin_width > 100:
        raise SystemExit("--bin_width must be between 0 and 100")

    # The graphs go into a histogram/ subfolder of the output directory --
    # by default the run's own directory, next to the CSV they came from --
    # so they sit apart from the profiler's own PNGs and CSV.
    output_dir = os.path.join(
        args.output_dir or os.path.dirname(os.path.abspath(args.csv_path)), 'histogram')
    os.makedirs(output_dir, exist_ok=True)

    cores = parse_core_list(args.cores) if args.cores else None
    df = pd.read_csv(args.csv_path)

    plot_pooled_core_usage(df, output_dir, args.bin_width, cores,
                           args.split_saturated, args.show)


if __name__ == '__main__':
    main()
