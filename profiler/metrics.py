"""Background sampling of system metrics into a CSV.

The CSV schema is unchanged from the Linux build so existing analysis scripts
keep working: a `Timestamp` column, the scalar metrics, then `core_<N>_usage`
and `core_<N>_frequency` columns flattened out of the per-core dicts.

Columns the machine cannot supply are written empty rather than zero-filled --
an empty cell means "not measured", which is very different from "0 watts".
"""
import atexit
import csv
import json
import os
import threading
import time
from datetime import datetime

import psutil

from . import hardware


def _flatten(metrics, timestamp):
    flat = {"Timestamp": timestamp}
    for key, value in metrics.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


class SystemMetricsLogger:
    """Samples system metrics on a daemon thread until `stop()` is called."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._buffer = []
        self._lock = threading.Lock()
        self._csv_file = None
        self._meta_file = None
        self._csv_write_interval = None
        self._last_csv_write = None
        self._ready = threading.Event()
        self._capabilities = []

        self._frequency = None
        self._monitor = None
        self._topology = {"hybrid": False, "core_class": {}, "physical_cores": None}

        # Ensure buffered samples survive an abrupt exit.
        atexit.register(self._flush_buffer_to_csv)

    # ------------------------------------------------------------- lifecycle
    def start(self, metrics_interval_ms=500, output_dir=".", csv_write_interval_s=None):
        if self._running:
            print("Logger is already running!")
            return

        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_file = os.path.join(output_dir, f"system_metrics_{timestamp}.csv")
        self._meta_file = os.path.join(output_dir, f"system_metrics_{timestamp}.json")

        open(self._csv_file, "w").close()

        self._metrics_interval = metrics_interval_ms / 1000
        self._csv_write_interval = csv_write_interval_s
        self._last_csv_write = time.time()

        self._running = True
        self._thread = threading.Thread(target=self._collect_metrics, daemon=True)
        self._thread.start()

        # Hardware handles are opened on the sampling thread (WMI objects are
        # bound to the COM apartment of the thread that created them), so wait
        # for it to publish what it managed to open before reporting.
        self._ready.wait(timeout=10)
        print("\nLogging started. Metric sources:")
        for line in self._capabilities:
            print(line)
        print()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        self._flush_buffer_to_csv()
        self._write_metadata()
        print(f"\nLogging stopped. CSV saved to: {self._csv_file}")
        return self._csv_file

    # -------------------------------------------------------------- sampling
    def _open_hardware(self):
        try:
            self._frequency = hardware.PerCoreFrequency()
            self._monitor = hardware.HardwareMonitor()
            self._topology = hardware.read_topology()
            self._capabilities = hardware.describe(self._frequency, self._monitor,
                                                   self._topology)
            # psutil's first percpu call returns 0.0 for every core because it
            # has no previous sample to diff against; burn that one here.
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception as exc:
            self._capabilities = [f"  [Warning] hardware probe failed: {exc}"]
        finally:
            # start() blocks on this; never leave it waiting.
            self._ready.set()

    def _sample(self):
        cpu_usage = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        core_usage = {f"core_{i}_usage": usage for i, usage in enumerate(per_core)}

        mhz = self._frequency.read() if self._frequency else {}
        core_freq = {f"core_{i}_frequency": mhz.get(i) for i in range(len(per_core))}

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            "cpu_usage": cpu_usage,
            "memory_usage": memory.percent,
            "total_memory": memory.total,
            "swap_usage": swap.percent,
            "total_swap": swap.total,
            "per_core_usage": core_usage,
            "per_core_freq": core_freq,
            "cpu_temperature": self._monitor.cpu_temperature_c() if self._monitor else None,
            "cpu_power": self._monitor.cpu_power_watts() if self._monitor else None,
        }

    def _collect_metrics(self):
        self._open_hardware()
        failures = 0
        try:
            while self._running:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                try:
                    sample = _flatten(self._sample(), stamp)
                except Exception as exc:
                    # One bad sample must not end the run; report the first few
                    # and keep going so the target stays profiled.
                    failures += 1
                    if failures <= 3:
                        print(f"[Warning] metrics sample failed: {exc}")
                    time.sleep(self._metrics_interval)
                    continue

                with self._lock:
                    self._buffer.append(sample)

                if self._csv_write_interval:
                    now = time.time()
                    if now - self._last_csv_write >= self._csv_write_interval:
                        self._flush_buffer_to_csv()
                        self._last_csv_write = now

                time.sleep(self._metrics_interval)
        finally:
            if failures:
                print(f"[Warning] {failures} metric sample(s) failed during this run")
            if self._frequency:
                self._frequency.close()

    # ----------------------------------------------------------------- output
    def _flush_buffer_to_csv(self):
        with self._lock:
            if not self._buffer:
                return
            file_empty = (not os.path.exists(self._csv_file)
                          or os.path.getsize(self._csv_file) == 0)
            with open(self._csv_file, mode="a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._buffer[0].keys())
                if file_empty:
                    writer.writeheader()
                writer.writerows(self._buffer)
            self._buffer.clear()

    def _write_metadata(self):
        """Sidecar describing the machine and which sensors actually worked.

        Written next to the CSV with the same timestamp so `organize_logs`
        files it into the same folder. Plotting reads it to label cores
        correctly on hybrid CPUs.
        """
        if not self._meta_file:
            return
        meta = {
            "platform": "Windows",
            "logical_processors": psutil.cpu_count(),
            "physical_cores": self._topology.get("physical_cores"),
            "hybrid_cpu": self._topology.get("hybrid", False),
            "core_class": {str(k): v for k, v in self._topology.get("core_class", {}).items()},
            "base_clock_mhz": self._frequency.base_mhz if self._frequency else None,
            "frequency_source": self._frequency.source if self._frequency else None,
            "power_temperature_source": self._monitor.provider if self._monitor else None,
        }
        try:
            with open(self._meta_file, "w") as f:
                json.dump(meta, f, indent=2)
        except OSError as exc:
            print(f"[Warning] could not write run metadata: {exc}")


if __name__ == "__main__":
    logger = SystemMetricsLogger()
    logger.start(metrics_interval_ms=500, output_dir=".", csv_write_interval_s=5)
    time.sleep(20)
    logger.stop()
