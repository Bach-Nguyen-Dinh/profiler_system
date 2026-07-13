import os
import sys
import glob
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator


def _relative_time(df):
    """Return a relative-time-in-seconds series computed from the Timestamp column."""
    ts = pd.to_datetime(df['Timestamp'])
    return (ts - ts.iloc[0]).dt.total_seconds()


def plot_power_compare(folder, blue_label=None, red_label=None):
    print(f"\nComparing power consumption from files in: {folder}")

    csv_files = sorted(glob.glob(os.path.join(folder, '*.csv')))
    if len(csv_files) != 2:
        raise SystemExit(
            f"Expected exactly 2 CSV files in {folder}, found {len(csv_files)}: {csv_files}"
        )

    # Load both files
    dfs = []
    for path in csv_files:
        df = pd.read_csv(path)
        # Forward-fill negative power values (e.g. RAPL counter wrap)
        df['cpu_power'] = df['cpu_power'].mask(df['cpu_power'] < 0).ffill()
        df['RelativeTime'] = _relative_time(df)
        dfs.append(df)

    # Clip both to the duration of the shorter run so both span the same time window
    # Statistics (avg/median) are computed over each file's ENTIRE sample space.
    # The plot itself is clipped to the shorter run's duration purely for visual
    # alignment, so the longer run only shows the matching time window.
    durations = [df['RelativeTime'].iloc[-1] for df in dfs]
    max_time = min(durations)
    print(f"Run durations: {durations[0]:.2f}s, {durations[1]:.2f}s -> "
          f"stats over full data, plot clipped to first {max_time:.2f}s")

    # Fixed color assignment (never user-controlled): the first file (sorted) is
    # always blue, the second is always red. This is stable across runs so the
    # user can look at the first plot, see which line is which color, then re-run
    # passing --blue / --red to add a descriptive suffix to that line.
    colors = ['tab:blue', 'tab:red']
    color_names = ['blue', 'red']
    suffixes = [blue_label, red_label]

    fig, ax = plt.subplots(figsize=(14, 8))

    for df, path, color, color_name, suffix in zip(dfs, csv_files, colors, color_names, suffixes):
        label = os.path.splitext(os.path.basename(path))[0]
        if suffix:
            label = f'{label} - {suffix}'

        # avg/median over the full run
        avg = np.mean(df['cpu_power'].values)
        median = np.median(df['cpu_power'].values)

        # only plot the clipped window for visual matching
        df_plot = df[df['RelativeTime'] <= max_time]
        power = df_plot['cpu_power'].values
        t = df_plot['RelativeTime'].values

        ax.plot(t, power, color=color, linewidth=2, alpha=0.85, label=f'{label} (power)')
        ax.axhline(avg, color=color, linestyle='--', linewidth=1.5, alpha=0.9,
                   label=f'{label} avg = {avg:.2f} W')
        ax.axhline(median, color=color, linestyle=':', linewidth=1.5, alpha=0.9,
                   label=f'{label} median = {median:.2f} W')

        print(f"  {label}: avg = {avg:.2f} W, median = {median:.2f} W ({color_name})")

    # Enrich the title only when both labels are provided (e.g. "32 cores vs 16 P-cores")
    if red_label and blue_label:
        title = f'CPU power consumption {red_label} vs {blue_label}'
    else:
        title = 'CPU power consumption comparison'
    ax.set_title(title)
    ax.set_ylabel('Power (W)')
    ax.set_xlabel('Time (s)')
    ax.grid(True, alpha=0.7)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
    ax.legend(loc='best', fontsize=10, frameon=True)

    plt.tight_layout()
    out_path = os.path.join(folder, 'power_comparison.png')
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved comparison plot to: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Plot CPU power consumption of 2 log files on the same graph for comparison."
    )
    parser.add_argument('folder', help="Folder containing exactly 2 metrics CSV files to compare.")
    parser.add_argument('--blue', default=None,
                        help="Descriptive label for the blue line (the first file). "
                             "Run once without it to see which file is blue.")
    parser.add_argument('--red', default=None,
                        help="Descriptive label for the red line (the second file). "
                             "Run once without it to see which file is red.")
    args = parser.parse_args()
    plot_power_compare(args.folder, blue_label=args.blue, red_label=args.red)
