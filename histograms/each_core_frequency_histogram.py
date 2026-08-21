"""Per-core frequency distribution (grouped bars, one group per core) from a profiler CSV.

Usage:
    python3 each_core_frequency_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                             [--max_freq 4000] [--show]
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

BINS = [0, 60, 70, 80, 90, 100]
LABELS = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']


def integer_ticks(axis):
    """Counts are whole numbers -- keep the tick marks off values like 2.5."""
    axis.set_major_locator(MaxNLocator(integer=True))


def plot_each_core_frequency(df, output_dir, max_freq, show, filename='each_core_frequency_histogram.png'):
    freq_columns = [col for col in df.columns if col.endswith('_frequency')]

    # Prepare counts matrix: rows=cores, cols=bins
    counts_matrix = []

    for col in freq_columns:
        freq_percent = (df[col] / max_freq) * 100
        bin_indices = np.digitize(freq_percent, BINS)
        counts = [np.sum(bin_indices == i) for i in range(1, len(BINS))]
        counts_matrix.append(counts)

    counts_matrix = np.array(counts_matrix)  # shape (cores, bins)

    # Plot grouped bar chart
    num_cores = len(freq_columns)
    num_bins = len(LABELS)
    bar_width = 0.8 / num_bins
    x = np.arange(num_cores)

    plt.figure(figsize=(15, 6))

    for i in range(num_bins):
        plt.bar(x + i * bar_width, counts_matrix[:, i], width=bar_width, label=LABELS[i])

    plt.xlabel("CPU Core")
    plt.ylabel("Number of samples")
    integer_ticks(plt.gca().yaxis)
    plt.title("CPU Core Frequency Distribution by Bins")
    plt.xticks(x + bar_width * (num_bins - 1) / 2, freq_columns, rotation=90)
    plt.legend(title="Frequency Range")
    plt.tight_layout()

    out_path = os.path.join(output_dir, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Wrote {out_path}")
    if show:
        plt.show()
    plt.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv_path',
                        help="Path to a system_metrics_<timestamp>.csv produced by the profiler")
    parser.add_argument('-o', '--output_dir', default=None,
                        help="Directory to write the PNG into, under a histogram/ subfolder of it "
                             "(default: the directory the input CSV is in)")
    parser.add_argument('--max_freq', type=float, default=4000,
                        help="Max CPU frequency in MHz used to normalize to a percentage (default: 4000)")
    parser.add_argument('--show', action='store_true',
                        help="Display the plot interactively in addition to saving it")
    return parser.parse_args()


def main():
    args = parse_args()
    # The graphs go into a histogram/ subfolder of the output directory --
    # by default the run's own directory, next to the CSV they came from --
    # so they sit apart from the profiler's own PNGs and CSV.
    output_dir = os.path.join(
        args.output_dir or os.path.dirname(os.path.abspath(args.csv_path)), 'histogram')
    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(args.csv_path)
    plot_each_core_frequency(df, output_dir, args.max_freq, args.show)


if __name__ == '__main__':
    main()
