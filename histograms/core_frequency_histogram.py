#################################################################################################################################
# Core Frequency Count Histogram
#################################################################################################################################
# import pandas as pd
# import matplotlib.pyplot as plt
# import numpy as np

# # Load CSV
# csv_path = "/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv"
# df = pd.read_csv(csv_path)

# # Select frequency columns
# freq_columns = [col for col in df.columns if col.endswith('_frequency')]

# # Extract frequencies as 1D array
# freq_data = df[freq_columns].values.flatten()

# # Max frequency in MHz
# max_freq = 4000

# # Normalize frequency to percentage
# freq_percent = (freq_data / max_freq) * 100

# # Define bins and labels
# bins = [0, 60, 70, 80, 90, 100]
# labels = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']

# # Digitize the frequency percentages into bins
# bin_indices = np.digitize(freq_percent, bins)

# # Count the number of samples in each bin
# counts = [np.sum(bin_indices == i) for i in range(1, len(bins))]

# # Plot the histogram
# plt.figure(figsize=(8,5))
# plt.bar(labels, counts, color='skyblue', edgecolor='black')
# plt.xlabel("Frequency Range (% of max frequency)")
# plt.ylabel("Number of Core Frequency Counts")
# plt.title("Histogram of CPU Core Frequencies")
# plt.grid(axis='y', linestyle='--', alpha=0.7)
# plt.savefig('/home/isabel/catkin_ws/histograms/core_frequency_count_histogram.png', dpi=300, bbox_inches='tight')
# plt.show()

#################################################################################################################################
# Core Average Frequency Histogram
#################################################################################################################################
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load CSV
csv_path = "/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv"
df = pd.read_csv(csv_path)

# Select frequency columns (per core)
freq_columns = [col for col in df.columns if col.endswith('_frequency')]

# Max frequency in MHz
max_freq = 4000

# Compute average frequency per core over all timestamps
core_avg_freq = df[freq_columns].mean()

# Normalize to percentage
core_avg_percent = (core_avg_freq / max_freq) * 100

# Define bins and labels
bins = [0, 60, 70, 80, 90, 100]
labels = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']

# Categorize cores into bins
categories = pd.cut(core_avg_percent, bins=bins, labels=labels, right=False)

# Count number of cores in each bin
counts = categories.value_counts().sort_index()

# Plot histogram
plt.figure(figsize=(8,5))
plt.bar(labels, counts, color='skyblue', edgecolor='black')
plt.xlabel("Average Core Frequency (% of max)")
plt.ylabel("Number of CPU Cores")
plt.title("CPU Cores by Average Frequency")
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig('/home/isabel/catkin_ws/histograms/core_frequency_average_histogram.png', dpi=300, bbox_inches='tight')
plt.show()
