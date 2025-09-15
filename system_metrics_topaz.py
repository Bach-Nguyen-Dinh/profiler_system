import psutil
import time
import threading
import csv
import os
import atexit
import stat
from datetime import datetime
import subprocess
import re
import glob

# ---------- Get System Metrics ----------
# def read_rapl_energy():
#     try:
#         with open("/sys/class/powercap/intel-rapl:0/energy_uj", "r") as f:
#             return int(f.read().strip())  # Energy in microjoules
#     except FileNotFoundError:
#         return None

# def get_cpu_power():
#     energy_start = read_rapl_energy()
#     t_start = time.time()
#     time.sleep(0.1)
#     energy_end = read_rapl_energy()
#     t_end = time.time()

#     if energy_start is None or energy_end is None:
#         return None

#     delta_energy_j = (energy_end - energy_start) / 1_000_000  # convert to joules
#     delta_time_s = t_end - t_start
#     power_watts = delta_energy_j / delta_time_s
#     return power_watts

def get_power_from_sensor(sensor_name="ina220-i2c-0-40"):
    try:
        # Run the sensors command
        output = subprocess.check_output(["sensors"], text=True)

        # Split into blocks (each sensor section is separated by blank lines)
        blocks = output.strip().split("\n\n")

        for block in blocks:
            if block.startswith(sensor_name):
                # Look for the power1 line inside the block
                match = re.search(r"power1:\s+([\d\.]+)\s*W", block)
                if match:
                    return float(match.group(1))
                else:
                    return None  # No power line found
        return None  # Sensor not found
    except subprocess.CalledProcessError as e:
        print("Error running sensors:", e)
        return None

def get_system_info():
    cpu_usage = psutil.cpu_percent(interval=None)
    per_core_usage = psutil.cpu_percent(interval=None, percpu=True)
    core_usage = {f"core_{i}_usage": usage for i, usage in enumerate(per_core_usage)}

    core_frequencies = {}

    # Try reading from sysfs first (Linux only)
    sysfs_paths = sorted(glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"))
    if sysfs_paths:
        for i, path in enumerate(sysfs_paths):
            try:
                with open(path) as f:
                    # scaling_cur_freq is in kHz, convert to MHz
                    core_frequencies[f"core_{i}_frequency"] = int(f.read().strip()) / 1000
            except Exception:
                core_frequencies[f"core_{i}_frequency"] = None
    elif hasattr(psutil, "cpu_freq"):
        # Fall back to psutil (may only return one object)
        freq_info = psutil.cpu_freq(percpu=True)
        if freq_info:
            for i, freq in enumerate(freq_info):
                core_frequencies[f"core_{i}_frequency"] = freq.current

    cpu_temp = None
    temps = {}
    sensor_data = psutil.sensors_temperatures()
    if sensor_data:
        for name, entries in sensor_data.items():
            for entry in entries:
                label = entry.label if entry.label else "unknown"
                temps[f"{name}_{label}"] = entry.current
    cpu_temp = max(temps.values())

    memory_usage = psutil.virtual_memory().percent
    total_memory = psutil.virtual_memory().total
    swap_usage = psutil.swap_memory().percent
    total_swap = psutil.swap_memory().total

    cpu_power = get_power_from_sensor("ina220-i2c-0-40")

    system_info = {
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "total_memory": total_memory,
        "swap_usage": swap_usage,
        "total_swap": total_swap,
        "per_core_usage": core_usage,
        "per_core_freq": core_frequencies,
        "cpu_temperature": cpu_temp,
        "cpu_power": cpu_power,
    }
    return system_info

# ---------- System Metrics Logger ----------
class SystemMetricsLogger:
    def __init__(self):
        self._running = False
        self._thread = None
        self._buffer = []
        self._lock = threading.Lock()
        self._csv_file = None
        self._csv_write_interval = None
        self._last_csv_write = None

        # Ensure data is saved on abrupt exit
        atexit.register(self._flush_buffer_to_csv)

    def start(self, metrics_interval_ms=100, output_dir=".", csv_write_interval_s=None):
        if self._running:
            print("Logger is already running!")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_file = os.path.join(output_dir, f"system_metrics_{timestamp}.csv")

        # Pre-create the file with wide permissions
        with open(self._csv_file, "w") as f:
            pass
        os.chmod(self._csv_file,
                stat.S_IRUSR | stat.S_IWUSR |
                stat.S_IRGRP | stat.S_IWGRP |
                stat.S_IROTH | stat.S_IWOTH)  # a+rw

        self._metrics_interval = metrics_interval_ms / 1000
        self._csv_write_interval = csv_write_interval_s
        self._last_csv_write = time.time()

        self._running = True
        self._thread = threading.Thread(target=self._collect_metrics, daemon=True)
        self._thread.start()
        print(f"\nLogging started\n")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        self._flush_buffer_to_csv()
        print(f"\nLogging stopped. CSV saved to: {self._csv_file}")
        return self._csv_file

    def _collect_metrics(self):
        while self._running:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            metrics = get_system_info()

            # Flatten per-core dictionaries, timestamp first
            flat_metrics = {"Timestamp": timestamp}
            for k, v in metrics.items():
                if isinstance(v, dict):
                    flat_metrics.update(v)
                else:
                    flat_metrics[k] = v

            # Append to buffer thread-safely
            with self._lock:
                self._buffer.append(flat_metrics)

            # Flush to CSV if needed
            if self._csv_write_interval:
                now = time.time()
                if now - self._last_csv_write >= self._csv_write_interval:
                    self._flush_buffer_to_csv()
                    self._last_csv_write = now

            time.sleep(self._metrics_interval)

    def _flush_buffer_to_csv(self):
        with self._lock:
            if not self._buffer:
                return

            file_empty = not os.path.exists(self._csv_file) or os.path.getsize(self._csv_file) == 0

            with open(self._csv_file, mode="a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._buffer[0].keys())
                if file_empty:
                    writer.writeheader()
                writer.writerows(self._buffer)

            self._buffer.clear()


# ---------- Example usage ----------
if __name__ == "__main__":
    logger = SystemMetricsLogger()
    # Start logging metrics every 500 ms, write to CSV every 5 seconds
    logger.start(metrics_interval_ms=500, output_dir=".", csv_write_interval_s=5)

    # Simulate your workflow running for 20 seconds
    time.sleep(20)

    out_file = logger.stop()
