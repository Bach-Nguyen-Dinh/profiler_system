import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

csv_path = "/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv"
df = pd.read_csv(csv_path)

freq_columns = [col for col in df.columns if col.endswith('_frequency')]
max_freq = 4000
bins = [0, 60, 70, 80, 90, 100]
labels = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']

# Prepare counts matrix: rows=cores, cols=bins
counts_matrix = []

for col in freq_columns:
    freq_percent = (df[col] / max_freq) * 100
    bin_indices = np.digitize(freq_percent, bins)
    counts = [np.sum(bin_indices == i) for i in range(1, len(bins))]
    counts_matrix.append(counts)

counts_matrix = np.array(counts_matrix)  # shape (cores, bins)

# Plot grouped bar chart
num_cores = len(freq_columns)
num_bins = len(labels)
bar_width = 0.8 / num_bins
x = np.arange(num_cores)

plt.figure(figsize=(15,6))

for i in range(num_bins):
    plt.bar(x + i*bar_width, counts_matrix[:, i], width=bar_width, label=labels[i])

plt.xlabel("CPU Core")
plt.ylabel("Number of samples")
plt.title("CPU Core Frequency Distribution by Bins")
plt.xticks(x + bar_width * (num_bins-1)/2, freq_columns, rotation=90)
plt.legend(title="Frequency Range")
plt.tight_layout()
plt.savefig('/home/isabel/catkin_ws/histograms/each_core_frequency_histogram.png', dpi=300, bbox_inches='tight')
plt.show()
