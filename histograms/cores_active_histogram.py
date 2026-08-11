#################################################################################################################################
# Average Utilisation
#################################################################################################################################
# import pandas as pd
# import matplotlib.pyplot as plt
# import numpy as np

# # Path to your CSV file
# csv_path = '/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv'

# # Load the data
# df = pd.read_csv(csv_path)

# # Extract core usage columns (all columns that end with '_usage' but are for cores)
# core_usage_cols = [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]

# # Calculate average utilization per core over all time samples
# core_avg_usage = df[core_usage_cols].mean()

# # Categorize cores based on average usage
# bins = [0, 25, 50, 75, 100.01]  # Extend last bin slightly to include 100%
# labels = ['<25%', '25-50%', '50-75%', '>75%']
# categories = pd.cut(core_avg_usage, bins=bins, labels=labels, right=True)  # right-inclusive

# # Count number of cores in each category
# counts = categories.value_counts().sort_index()

# # Plot histogram
# plt.figure(figsize=(8,5))
# counts.plot(kind='bar', color='skyblue', edgecolor='black')
# plt.title("Number of Cores Per Usage Range")
# plt.xlabel("CPU Usage Range (%)") 
# plt.ylabel("Number of CPU Cores")
# plt.grid(axis='y', linestyle='--', alpha=0.7)
# plt.tight_layout()
# plt.savefig('/home/isabel/catkin_ws/histograms/cores_active_average_usage_histogram.png', dpi=300, bbox_inches='tight')
# plt.show()

#################################################################################################################################
# Active Core Usage
#################################################################################################################################
# import pandas as pd
# import matplotlib.pyplot as plt
# import numpy as np

# # Path to your CSV file
# csv_path = '/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv'

# # Load the data
# df = pd.read_csv(csv_path)

# # Extract core usage columns (all columns that end with '_usage' but are for cores)
# core_usage_cols = [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]

# # Percentage of time each core is active
# core_active_pct = ((df[core_usage_cols] > 0).sum() / len(df)) * 100

# # Categorize cores based on average usage
# bins = [0, 70, 80, 90, 100.1]
# labels = ['<70%', '70-80%', '80-90%', '>90%']
# categories = pd.cut(core_active_pct, bins=bins, labels=labels, right=False)

# # Count number of cores in each category
# counts = categories.value_counts().sort_index()

# # Plot histogram
# plt.figure(figsize=(8,5))
# plt.bar(labels, counts, color='skyblue', edgecolor='black')
# plt.xlabel("Percentage of Time Core is Active")
# plt.ylabel("Number of CPU Cores")
# plt.title("Number of Cores Per Active-Time Range")
# plt.grid(axis='y', linestyle='--', alpha=0.7)
# plt.tight_layout()
# plt.savefig('/home/isabel/catkin_ws/histograms/cores_active_histogram.png', dpi=300, bbox_inches='tight')
# plt.show()

#################################################################################################################################
# Average Utilisation - Performance vs Efficiency Cores
#################################################################################################################################
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load CSV
csv_path = '/home/isabel/YOLO/bach_metrics/new_analyzer/profiler_system/logs/20251128_163813_5_minutes_with_gps/system_metrics_20251128_163813.csv'
df = pd.read_csv(csv_path)

# Extract core usage columns
core_usage_cols = [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]
core_ids = [int(col.split('_')[1]) for col in core_usage_cols]

# i9-13900E core layout - checked with 'lscpu -e'
PERFORMANCE_CORES = list(range(0, 16))     # core_0 to core_15  (8 P-cores, HT=16 threads)
EFFICIENCY_CORES  = list(range(16, 32))    # core_16 to core_31 (16 E-cores, 16 threads)

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

    if cid in PERFORMANCE_CORES:
        p_counts[category] += 1
    else:
        e_counts[category] += 1

# # Plot histogram
x = np.arange(len(labels))
width = 0.35

plt.figure(figsize=(8,5))
plt.bar(x - width/2, p_counts.values, width, color='skyblue', edgecolor='black', label='P-cores')
plt.bar(x + width/2, e_counts.values, width, color='orange', edgecolor='black', label='E-cores')

plt.xticks(x, labels)
plt.xlabel("Average CPU Core Usage (%)")
plt.ylabel("Number of Cores")
plt.title("Core Usage Distribution (P-cores vs E-cores)")
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.legend()
plt.tight_layout()
plt.savefig('/home/isabel/catkin_ws/histograms/cores_active_average_usage_p_and_e_core_histogram.png', dpi=300, bbox_inches='tight')
plt.show()
