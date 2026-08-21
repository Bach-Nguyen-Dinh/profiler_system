"""Core-utilisation histograms from a profiler CSV.

Usage:
    python3 cores_active_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                      [--plots average active p_and_e]
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


def core_usage_columns(df):
    """Per-core usage columns, by the `core_<N>_usage` naming convention."""
    return [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]


def integer_ticks(axis):
    """Counts are whole numbers -- keep the tick marks off values like 2.5."""
    axis.set_major_locator(MaxNLocator(integer=True))


#################################################################################################################################
# Average Utilisation
#################################################################################################################################
def plot_average_usage(df, output_dir, p_cores, show):
    core_usage_cols = core_usage_columns(df)

    # Calculate average utilization per core over all time samples
    core_avg_usage = df[core_usage_cols].mean()

    # Categorize cores based on average usage
    bins = [0, 25, 50, 75, 100.01]  # Extend last bin slightly to include 100%
    labels = ['<25%', '25-50%', '50-75%', '>75%']
    categories = pd.cut(core_avg_usage, bins=bins, labels=labels, right=True)  # right-inclusive

    # Count number of cores in each category
    counts = categories.value_counts().sort_index()

    # Plot histogram
    plt.figure(figsize=(8, 5))
    counts.plot(kind='bar', color='skyblue', edgecolor='black')
    plt.title("Number of Cores Per Usage Range")
    plt.xlabel("CPU Usage Range (%)")
    plt.ylabel("Number of CPU Cores")
    integer_ticks(plt.gca().yaxis)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    save(output_dir, 'cores_active_average_usage_histogram.png', show)


#################################################################################################################################
# Active Core Usage
#################################################################################################################################
def plot_active_time(df, output_dir, p_cores, show):
    core_usage_cols = core_usage_columns(df)

    # Percentage of time each core is active
    core_active_pct = ((df[core_usage_cols] > 0).sum() / len(df)) * 100

    # Categorize cores based on active time
    bins = [0, 70, 80, 90, 100.1]
    labels = ['<70%', '70-80%', '80-90%', '>90%']
    categories = pd.cut(core_active_pct, bins=bins, labels=labels, right=False)

    # Count number of cores in each category
    counts = categories.value_counts().sort_index()

    # Plot histogram
    plt.figure(figsize=(8, 5))
    plt.bar(labels, counts, color='skyblue', edgecolor='black')
    plt.xlabel("Percentage of Time Core is Active")
    plt.ylabel("Number of CPU Cores")
    integer_ticks(plt.gca().yaxis)
    plt.title("Number of Cores Per Active-Time Range")
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    save(output_dir, 'cores_active_histogram.png', show)


#################################################################################################################################
# Average Utilisation - Performance vs Efficiency Cores
#################################################################################################################################
def plot_p_and_e_usage(df, output_dir, p_cores, show):
    core_usage_cols = core_usage_columns(df)
    core_ids = [int(col.split('_')[1]) for col in core_usage_cols]

    # Compute average usage per logical CPU thread
    core_avg_usage = df[core_usage_cols].mean()

    # Bins
    bins = [0, 25, 50, 75, 100.01]
    labels = ['<25%', '25-50%', '50-75%', '>75%']

    # Init counts
    p_counts = pd.Series(0, index=labels)
    e_counts = pd.Series(0, index=labels)

    # Assign each core to a bin (P or E)
    for col, cid, avg in zip(core_usage_cols, core_ids, core_avg_usage):
        category = pd.cut([avg], bins=bins, labels=labels, right=True)[0]

        if cid in p_cores:
            p_counts[category] += 1
        else:
            e_counts[category] += 1

    # Plot histogram
    x = np.arange(len(labels))
    width = 0.35

    plt.figure(figsize=(8, 5))
    plt.bar(x - width / 2, p_counts.values, width, color='skyblue', edgecolor='black', label='P-cores')
    plt.bar(x + width / 2, e_counts.values, width, color='orange', edgecolor='black', label='E-cores')

    plt.xticks(x, labels)
    plt.xlabel("Average CPU Core Usage (%)")
    plt.ylabel("Number of Cores")
    integer_ticks(plt.gca().yaxis)
    plt.title("Core Usage Distribution (P-cores vs E-cores)")
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    save(output_dir, 'cores_active_average_usage_p_and_e_core_histogram.png', show)


def save(output_dir, filename, show):
    out_path = os.path.join(output_dir, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Wrote {out_path}")
    if show:
        plt.show()
    plt.close()


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


PLOTS = {
    'average': plot_average_usage,
    'active': plot_active_time,
    'p_and_e': plot_p_and_e_usage,
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv_path',
                        help="Path to a system_metrics_<timestamp>.csv produced by the profiler")
    parser.add_argument('-o', '--output_dir', default=None,
                        help="Directory to write the PNGs into, under a histogram/ subfolder of it "
                             "(default: the directory the input CSV is in)")
    parser.add_argument('--plots', nargs='+', choices=sorted(PLOTS), default=sorted(PLOTS),
                        help="Which histograms to generate (default: all)")
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

    p_cores = parse_core_list(args.p_cores)
    df = pd.read_csv(args.csv_path)

    for name in args.plots:
        PLOTS[name](df, output_dir, p_cores, args.show)


if __name__ == '__main__':
    main()
