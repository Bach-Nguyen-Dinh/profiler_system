import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np

# Read the CSV data
input_filename = 'system_metrics_20250909_095831.csv'
df = pd.read_csv(input_filename)

# Extract timestamp from filename for output files
timestamp = input_filename.split('_')[2] + '_' + input_filename.split('_')[3].split('.')[0]

# Convert timestamp to datetime
df['Timestamp'] = pd.to_datetime(df['Timestamp'])

# Set up the figure with subplots
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle('System Performance Metrics', fontsize=16, fontweight='bold')

# 1. Memory Usage
ax1 = axes[0, 0]
ax1.plot(df['Timestamp'].values, df['memory_usage'].values, 'b-', linewidth=2, label='Memory Usage %')
ax1.set_title('Memory Usage Over Time')
ax1.set_ylabel('Memory Usage (%)')
ax1.grid(True, alpha=0.3)
ax1.legend()
ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

# Save memory usage subplot
fig1 = plt.figure(figsize=(10, 6))
ax1_solo = fig1.add_subplot(111)
ax1_solo.plot(df['Timestamp'].values, df['memory_usage'].values, 'b-', linewidth=2, label='Memory Usage %')
ax1_solo.set_title('Memory Usage Over Time')
ax1_solo.set_ylabel('Memory Usage (%)')
ax1_solo.set_xlabel('Time')
ax1_solo.grid(True, alpha=0.3)
ax1_solo.legend()
ax1_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax1_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'memory_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig1)

# 2. CPU Cores Usage
ax2 = axes[0, 1]
core_columns = [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]
colors = plt.cm.tab10(np.linspace(0, 1, len(core_columns)))

for i, core_col in enumerate(core_columns):
    core_num = core_col.split('_')[1]
    ax2.plot(df['Timestamp'].values, df[core_col].values, color=colors[i], 
             linewidth=1.5, label=f'Core {core_num}', alpha=0.8)

ax2.set_title('CPU Cores Usage Over Time')
ax2.set_ylabel('CPU Usage (%)')
ax2.grid(True, alpha=0.3)
ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

# Save CPU cores usage subplot
fig2 = plt.figure(figsize=(12, 6))
ax2_solo = fig2.add_subplot(111)
for i, core_col in enumerate(core_columns):
    core_num = core_col.split('_')[1]
    ax2_solo.plot(df['Timestamp'].values, df[core_col].values, color=colors[i], 
                  linewidth=1.5, label=f'Core {core_num}', alpha=0.8)
ax2_solo.set_title('CPU Cores Usage Over Time')
ax2_solo.set_ylabel('CPU Usage (%)')
ax2_solo.set_xlabel('Time')
ax2_solo.grid(True, alpha=0.3)
ax2_solo.legend()
ax2_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax2_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'cpu_cores_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig2)

# 3. CPU Cores Frequency
ax3 = axes[0, 2]
freq_columns = [col for col in df.columns if col.startswith('core_') and col.endswith('_frequency')]

for i, freq_col in enumerate(freq_columns):
    core_num = freq_col.split('_')[1]
    ax3.plot(df['Timestamp'].values, df[freq_col].values, color=colors[i], 
             linewidth=1.5, label=f'Core {core_num}', alpha=0.8)

ax3.set_title('CPU Cores Frequency Over Time')
ax3.set_ylabel('Frequency (MHz)')
ax3.grid(True, alpha=0.3)
ax3.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

# Save CPU cores frequency subplot
fig3 = plt.figure(figsize=(12, 6))
ax3_solo = fig3.add_subplot(111)
for i, freq_col in enumerate(freq_columns):
    core_num = freq_col.split('_')[1]
    ax3_solo.plot(df['Timestamp'].values, df[freq_col].values, color=colors[i], 
                  linewidth=1.5, label=f'Core {core_num}', alpha=0.8)
ax3_solo.set_title('CPU Cores Frequency Over Time')
ax3_solo.set_ylabel('Frequency (MHz)')
ax3_solo.set_xlabel('Time')
ax3_solo.grid(True, alpha=0.3)
ax3_solo.legend()
ax3_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax3_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'cpu_cores_frequency_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig3)

# 4. CPU Power
ax4 = axes[1, 0]
ax4.plot(df['Timestamp'].values, df['cpu_power'].values, 'r-', linewidth=2, label='CPU Power')
ax4.set_title('CPU Power Consumption Over Time')
ax4.set_ylabel('Power (Watts)')
ax4.set_xlabel('Time')
ax4.grid(True, alpha=0.3)
ax4.legend()
ax4.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)

# Save CPU power subplot
fig4 = plt.figure(figsize=(10, 6))
ax4_solo = fig4.add_subplot(111)
ax4_solo.plot(df['Timestamp'].values, df['cpu_power'].values, 'r-', linewidth=2, label='CPU Power')
ax4_solo.set_title('CPU Power Consumption Over Time')
ax4_solo.set_ylabel('Power (Watts)')
ax4_solo.set_xlabel('Time')
ax4_solo.grid(True, alpha=0.3)
ax4_solo.legend()
ax4_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax4_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'cpu_power_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig4)

# 5. CPU Temperature
ax5 = axes[1, 1]
ax5.plot(df['Timestamp'].values, df['cpu_temperature'].values, 'orange', linewidth=2, label='CPU Temperature')
ax5.set_title('CPU Temperature Over Time')
ax5.set_ylabel('Temperature (°C)')
ax5.set_xlabel('Time')
ax5.grid(True, alpha=0.3)
ax5.legend()
ax5.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45)

# Save CPU temperature subplot
fig5 = plt.figure(figsize=(10, 6))
ax5_solo = fig5.add_subplot(111)
ax5_solo.plot(df['Timestamp'].values, df['cpu_temperature'].values, 'orange', linewidth=2, label='CPU Temperature')
ax5_solo.set_title('CPU Temperature Over Time')
ax5_solo.set_ylabel('Temperature (°C)')
ax5_solo.set_xlabel('Time')
ax5_solo.grid(True, alpha=0.3)
ax5_solo.legend()
ax5_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax5_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'cpu_temperature_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig5)

# 6. Overall CPU Usage
ax6 = axes[1, 2]
ax6.plot(df['Timestamp'].values, df['cpu_usage'].values, 'g-', linewidth=2, label='Overall CPU Usage')
ax6.set_title('Overall CPU Usage Over Time')
ax6.set_ylabel('CPU Usage (%)')
ax6.set_xlabel('Time')
ax6.grid(True, alpha=0.3)
ax6.legend()
ax6.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax6.xaxis.get_majorticklabels(), rotation=45)

# Save overall CPU usage subplot
fig6 = plt.figure(figsize=(10, 6))
ax6_solo = fig6.add_subplot(111)
ax6_solo.plot(df['Timestamp'].values, df['cpu_usage'].values, 'g-', linewidth=2, label='Overall CPU Usage')
ax6_solo.set_title('Overall CPU Usage Over Time')
ax6_solo.set_ylabel('CPU Usage (%)')
ax6_solo.set_xlabel('Time')
ax6_solo.grid(True, alpha=0.3)
ax6_solo.legend()
ax6_solo.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
plt.setp(ax6_solo.xaxis.get_majorticklabels(), rotation=45)
plt.tight_layout()
plt.savefig(f'overall_cpu_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
plt.close(fig6)

# Adjust layout to prevent overlap
plt.tight_layout()

# Display statistics
print("System Metrics Summary:")
print("=" * 50)
print(f"Memory Usage - Avg: {df['memory_usage'].mean():.1f}%, Max: {df['memory_usage'].max():.1f}%")
print(f"CPU Usage - Avg: {df['cpu_usage'].mean():.1f}%, Max: {df['cpu_usage'].max():.1f}%")
print(f"CPU Power - Avg: {df['cpu_power'].mean():.1f}W, Max: {df['cpu_power'].max():.1f}W")
print(f"CPU Temperature - Avg: {df['cpu_temperature'].mean():.1f}°C, Max: {df['cpu_temperature'].max():.1f}°C")

# Optional: Save the combined figure
plt.savefig(f'system_metrics_dashboard_{timestamp}.png', dpi=300, bbox_inches='tight')

# Print saved files
print("\nSaved files:")
print("=" * 30)
print(f"memory_usage_{timestamp}.png")
print(f"cpu_cores_usage_{timestamp}.png")
print(f"cpu_cores_frequency_{timestamp}.png")
print(f"cpu_power_{timestamp}.png")
print(f"cpu_temperature_{timestamp}.png")
print(f"overall_cpu_usage_{timestamp}.png")
print(f"system_metrics_dashboard_{timestamp}.png")