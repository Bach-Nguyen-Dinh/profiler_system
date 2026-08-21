"""Core frequency histograms from a profiler CSV.

Usage:
    python3 core_frequency_histogram.py <system_metrics_*.csv> [-o OUT_DIR]
                                        [--max_freq 4000] [--plots count average]
                                        [--show]
"""

import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

# Frequency bins, shared by both plots
BINS = [0, 60, 70, 80, 90, 100]
LABELS = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']


def load_frequency_columns(df):
    """Per-core frequency columns, by the `core_<N>_frequency` naming convention."""
    return [col for col in df.columns if col.endswith('_frequency')]


def integer_ticks(axis):
    """Counts are whole numbers -- keep the tick marks off values like 2.5."""
    axis.set_major_locator(MaxNLocator(integer=True))


#################################################################################################################################
# Core Frequency Count Histogram
#################################################################################################################################
def plot_frequency_count(df, output_dir, max_freq, show):
    freq_columns = load_frequency_columns(df)

    # Extract frequencies as 1D array
    freq_data = df[freq_columns].values.flatten()

    # Normalize frequency to percentage
    freq_percent = (freq_data / max_freq) * 100

    # Digitize the frequency percentages into bins
    bin_indices = np.digitize(freq_percent, BINS)

    # Count the number of samples in each bin
    counts = [np.sum(bin_indices == i) for i in range(1, len(BINS))]

    # Plot the histogram
    plt.figure(figsize=(8, 5))
    plt.bar(LABELS, counts, color='skyblue', edgecolor='black')
    plt.xlabel("Frequency Range (% of max frequency)")
    plt.ylabel("Number of Core Frequency Counts")
    integer_ticks(plt.gca().yaxis)
    plt.title("Histogram of CPU Core Frequencies")
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    save(output_dir, 'core_frequency_count_histogram.png', show)


#################################################################################################################################
# Core Average Frequency Histogram
#################################################################################################################################
def plot_frequency_average(df, output_dir, max_freq, show):
    freq_columns = load_frequency_columns(df)

    # Compute average frequency per core over all timestamps
    core_avg_freq = df[freq_columns].mean()

    # Normalize to percentage
    core_avg_percent = (core_avg_freq / max_freq) * 100

    # Categorize cores into bins
    categories = pd.cut(core_avg_percent, bins=BINS, labels=LABELS, right=False)

    # Count number of cores in each bin
    counts = categories.value_counts().sort_index()

    # Plot histogram
    plt.figure(figsize=(8, 5))
    plt.bar(LABELS, counts, color='skyblue', edgecolor='black')
    plt.xlabel("Average Core Frequency (% of max)")
    plt.ylabel("Number of CPU Cores")
    integer_ticks(plt.gca().yaxis)
    plt.title("CPU Cores by Average Frequency")
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    save(output_dir, 'core_frequency_average_histogram.png', show)


def save(output_dir, filename, show):
    out_path = os.path.join(output_dir, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Wrote {out_path}")
    if show:
        plt.show()
    plt.close()


PLOTS = {
    'count': plot_frequency_count,
    'average': plot_frequency_average,
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('csv_path',
                        help="Path to a system_metrics_<timestamp>.csv produced by the profiler")
    parser.add_argument('-o', '--output_dir', default=None,
                        help="Directory to write the PNGs into, under a histogram/ subfolder of it "
                             "(default: the directory the input CSV is in)")
    parser.add_argument('--max_freq', type=float, default=4000,
                        help="Max CPU frequency in MHz used to normalize to a percentage (default: 4000)")
    parser.add_argument('--plots', nargs='+', choices=sorted(PLOTS), default=sorted(PLOTS),
                        help="Which histograms to generate (default: all)")
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

    df = pd.read_csv(args.csv_path)

    for name in args.plots:
        PLOTS[name](df, output_dir, args.max_freq, args.show)


if __name__ == '__main__':
    main()
