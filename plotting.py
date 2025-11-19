import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np

from matplotlib.ticker import MaxNLocator

INPUT_FILE = 'system_metrics_20251114_113629.csv'

def plot_system_metrics(input_filename=INPUT_FILE):
    print("\nPlotting the logs")
    # Read the CSV data
    df = pd.read_csv(input_filename)

    # Extract timestamp from filename for output files
    timestamp = input_filename.split('_')[2] + '_' + input_filename.split('_')[3].split('.')[0]

    # Convert timestamp to datetime
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Safeguard: Replace negative values with the previous valid value
    numeric_columns = df.select_dtypes(include=[np.number]).columns
    for col in numeric_columns:
        # Set negative values to NaN, then forward fill with previous value
        df[col] = df[col].mask(df[col] < 0).ffill()
    
    # Create relative time column in seconds
    first_timestamp = df['Timestamp'].iloc[0]
    df['RelativeTime'] = (df['Timestamp'] - first_timestamp).dt.total_seconds()

    # Calculate the time span to choose appropriate tick intervals
    time_span = df['RelativeTime'].max() - df['RelativeTime'].min()
    print(f"Time span: {time_span:.1f} seconds ({time_span/60:.1f} minutes)")

    # Dynamically scale time units: seconds or hours
    if time_span >= 3600:  # 60 minutes or more
        df['RelativeTime'] = df['RelativeTime'] / 3600  # Convert to hours
        time_label = 'Time (h)'
        print(f"Time axis will be displayed in hours ({time_span/3600:.1f} hours)")
    else:
        time_label = 'Time (s)'
        print(f"Time axis will be displayed in seconds")

    # Use conservative tick intervals based on time span in seconds
    # Always limit to maximum 10-15 ticks regardless of time span
    if time_span <= 60:  # Less than 1 minute
        major_locator = MaxNLocator(nbins=10)
    elif time_span <= 300:  # Less than 5 minutes
        major_locator = MaxNLocator(nbins=8)
    elif time_span <= 1800:  # Less than 30 minutes
        major_locator = MaxNLocator(nbins=6)
    elif time_span <= 3600:  # Less than 1 hour
        major_locator = MaxNLocator(nbins=6)
    else:  # More than 1 hour - be very conservative
        major_locator = MaxNLocator(nbins=5)

    # Set up the figure with subplots
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))

    # 1. Memory Usage
    ax1 = axes[0, 0]
    ax1.plot(df['RelativeTime'].values, df['memory_usage'].values * df['total_memory'].values / 100 / (1024**3), 'b-', linewidth=2, label='Memory usage')
    ax1.set_title('Memory usage over time')
    ax1.set_ylabel('Memory usage (GB)')
    ax1.set_xlabel(time_label)
    ax1.grid(True, alpha=0.7)
    ax1.legend()
    ax1.xaxis.set_major_locator(major_locator)

    # Save memory usage subplot
    fig1 = plt.figure(figsize=(10, 6))
    ax1_solo = fig1.add_subplot(111)
    ax1_solo.plot(df['RelativeTime'].values, df['memory_usage'].values * df['total_memory'].values / 100 / (1024**3), 'b-', linewidth=2, label='Memory usage')
    ax1_solo.set_title('Memory usage over time')
    ax1_solo.set_ylabel('Memory usage (GB)')
    ax1_solo.set_xlabel(time_label)
    ax1_solo.grid(True, alpha=0.7)
    ax1_solo.legend()
    ax1_solo.xaxis.set_major_locator(major_locator)
    plt.tight_layout()
    plt.savefig(f'memory_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig1)

    print("Plotted Memory Usage")

    # 2. CPU Cores Usage
    ax2 = axes[0, 1]
    core_columns = [col for col in df.columns if col.startswith('core_') and col.endswith('_usage')]
    colors = plt.cm.tab10(np.linspace(0, 1, len(core_columns)))

    for i, core_col in enumerate(core_columns):
        core_num = core_col.split('_')[1]
        ax2.plot(df['RelativeTime'].values, df[core_col].values, color=colors[i], 
                linewidth=1.5, label=f'Core {core_num}', alpha=0.8)

    ax2.set_title('CPU cores usage over time')
    ax2.set_ylabel('CPU usage (%)')
    ax2.set_xlabel(time_label)
    ax2.grid(True, alpha=0.7)
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.xaxis.set_major_locator(major_locator)
    ax2.set_ylim(-5, 105)  # Visual padding
    ax2.set_yticks(range(0, 101, 20))  # Only show ticks from 0 to 100, every 20%

    # Save CPU cores usage subplot
    fig2 = plt.figure(figsize=(12, 6))
    ax2_solo = fig2.add_subplot(111)
    for i, core_col in enumerate(core_columns):
        core_num = core_col.split('_')[1]
        ax2_solo.plot(df['RelativeTime'].values, df[core_col].values, color=colors[i], 
                    linewidth=1.5, label=f'Core {core_num}', alpha=0.8)
    ax2_solo.set_title('CPU cores usage over time')
    ax2_solo.set_ylabel('CPU usage (%)')
    ax2_solo.set_xlabel(time_label)
    ax2_solo.grid(True, alpha=0.7)
    ax2_solo.legend()
    ax2_solo.xaxis.set_major_locator(major_locator)
    ax2_solo.set_ylim(-5, 105)  # Visual padding
    ax2_solo.set_yticks(range(0, 101, 20))  # Only show ticks from 0 to 100, every 20%
    plt.tight_layout()
    plt.savefig(f'cpu_cores_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig2)

    print("Plotted CPU Cores Usage")

    # 3. CPU Cores Frequency
    ax3 = axes[0, 2]
    freq_columns = [col for col in df.columns if col.startswith('core_') and col.endswith('_frequency')]

    for i, freq_col in enumerate(freq_columns):
        core_num = freq_col.split('_')[1]
        ax3.plot(df['RelativeTime'].values, df[freq_col].values, color=colors[i], 
                linewidth=1.5, label=f'Core {core_num}', alpha=0.8)

    ax3.set_title('CPU cores frequency over time')
    ax3.set_ylabel('Frequency (MHz)')
    ax3.set_xlabel(time_label)
    ax3.grid(True, alpha=0.7)
    ax3.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax3.xaxis.set_major_locator(major_locator)

    # Save CPU cores frequency subplot
    fig3 = plt.figure(figsize=(12, 6))
    ax3_solo = fig3.add_subplot(111)
    for i, freq_col in enumerate(freq_columns):
        core_num = freq_col.split('_')[1]
        ax3_solo.plot(df['RelativeTime'].values, df[freq_col].values, color=colors[i], 
                    linewidth=1.5, label=f'Core {core_num}', alpha=0.8)
    ax3_solo.set_title('CPU cores frequency over time')
    ax3_solo.set_ylabel('Frequency (MHz)')
    ax3_solo.set_xlabel(time_label)
    ax3_solo.grid(True, alpha=0.7)
    ax3_solo.legend()
    ax3_solo.xaxis.set_major_locator(major_locator)
    plt.tight_layout()
    plt.savefig(f'cpu_cores_frequency_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig3)

    print("Plotted CPU Cores Frequency")

    # 4. CPU Power
    ax4 = axes[1, 0]
    ax4.plot(df['RelativeTime'].values, df['cpu_power'].values, 'r-', linewidth=2, label='CPU power')
    ax4.set_title('CPU power consumption over time')
    ax4.set_ylabel('Power (W)')
    ax4.set_xlabel(time_label)
    ax4.grid(True, alpha=0.7)
    ax4.legend()
    ax4.xaxis.set_major_locator(major_locator)

    # Save CPU power subplot
    fig4 = plt.figure(figsize=(10, 6))
    ax4_solo = fig4.add_subplot(111)
    ax4_solo.plot(df['RelativeTime'].values, df['cpu_power'].values, 'r-', linewidth=2, label='CPU power')
    ax4_solo.set_title('CPU power consumption over time')
    ax4_solo.set_ylabel('Power (W)')
    ax4_solo.set_xlabel(time_label)
    ax4_solo.grid(True, alpha=0.7)
    ax4_solo.legend()
    ax4_solo.xaxis.set_major_locator(major_locator)
    plt.tight_layout()
    plt.savefig(f'cpu_power_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig4)

    print("Plotted CPU Power Consumption")

    # 5. CPU Temperature
    ax5 = axes[1, 1]
    ax5.plot(df['RelativeTime'].values, df['cpu_temperature'].values, 'orange', linewidth=2, label='CPU temperature')
    ax5.set_title('CPU temperature over time')
    ax5.set_ylabel('Temperature (°C)')
    ax5.set_xlabel(time_label)
    ax5.grid(True, alpha=0.7)
    ax5.legend()
    ax5.xaxis.set_major_locator(major_locator)

    # Save CPU temperature subplot
    fig5 = plt.figure(figsize=(10, 6))
    ax5_solo = fig5.add_subplot(111)
    ax5_solo.plot(df['RelativeTime'].values, df['cpu_temperature'].values, 'orange', linewidth=2, label='CPU temperature')
    ax5_solo.set_title('CPU temperature over time')
    ax5_solo.set_ylabel('Temperature (°C)')
    ax5_solo.set_xlabel(time_label)
    ax5_solo.grid(True, alpha=0.7)
    ax5_solo.legend()
    ax5_solo.xaxis.set_major_locator(major_locator)
    plt.tight_layout()
    plt.savefig(f'cpu_temperature_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig5)

    print("Plotted CPU Temperature")

    # 6. Overall CPU Usage
    ax6 = axes[1, 2]
    ax6.plot(df['RelativeTime'].values, df['cpu_usage'].values, 'g-', linewidth=2, label='Overall CPU usage')
    ax6.set_title('Overall CPU usage over time')
    ax6.set_ylabel('CPU usage (%)')
    ax6.set_xlabel(time_label)
    ax6.grid(True, alpha=0.7)
    ax6.legend()
    ax6.xaxis.set_major_locator(major_locator)
    ax6.set_ylim(-5, 105)  # Visual padding
    ax6.set_yticks(range(0, 101, 20))  # Only show ticks from 0 to 100, every 20%

    # Save overall CPU usage subplot
    fig6 = plt.figure(figsize=(10, 6))
    ax6_solo = fig6.add_subplot(111)
    ax6_solo.plot(df['RelativeTime'].values, df['cpu_usage'].values, 'g-', linewidth=2, label='Overall CPU usage')
    ax6_solo.set_title('Overall CPU usage over time')
    ax6_solo.set_ylabel('CPU usage (%)')
    ax6_solo.set_xlabel(time_label)
    ax6_solo.grid(True, alpha=0.7)
    ax6_solo.legend()
    ax6_solo.xaxis.set_major_locator(major_locator)
    ax6_solo.set_ylim(-5, 105)  # Visual padding
    ax6_solo.set_yticks(range(0, 101, 20))  # Only show ticks from 0 to 100, every 20%
    plt.tight_layout()
    plt.savefig(f'overall_cpu_usage_{timestamp}.png', dpi=300, bbox_inches='tight')
    plt.close(fig6)

    print("Plotted Overall CPU Usage")

    # Adjust layout to prevent overlap
    plt.tight_layout()

    # Optional: Save the combined figure
    plt.savefig(f'system_metrics_dashboard_{timestamp}.png', dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    plot_system_metrics(INPUT_FILE)