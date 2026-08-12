"""Background sampling of system metrics into a CSV.

The CSV schema is unchanged from the Linux build so existing analysis scripts
keep working: a `Timestamp` column, the scalar metrics, then `core_<N>_usage`
and `core_<N>_frequency` columns flattened out of the per-core dicts.

Power is required: if its source is missing the run is aborted before the
target program starts, rather than producing a CSV with an empty power column.
Temperature and frequency are best-effort, because on Windows they genuinely
may not exist -- a machine whose firmware declares no ACPI thermal zone has no
CPU temperature to give any user-mode program, and refusing to profile it at
all would help nobody. Any cell that could not be sampled is written empty
rather than zero-filled: an empty cell means "not measured", which is very
different from "0 watts".
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


class MetricsUnavailableError(RuntimeError):
    """A required metric source could not be opened; the run must not start."""


class _Range:
    """Min/max/count of a series, tracked without keeping the series."""

    def __init__(self):
        self.count = 0
        self.low = None
        self.high = None

    def add(self, value):
        if value is None:
            return
        self.count += 1
        if self.low is None or value < self.low:
            self.low = value
        if self.high is None or value > self.high:
            self.high = value

    @property
    def spread(self):
        if self.low is None:
            return None
        return self.high - self.low


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
        self._sensor_gaps = 0
        self._probe_error = None
        self._temperature_expected = False

        self._frequency = None
        self._energy = None
        self._thermal = None
        self._topology = {"hybrid": False, "core_class": {}, "physical_cores": None}

        # Spread of the temperature against the spread of the CPU load, so
        # stop() can tell a working thermal zone from a firmware constant.
        self._temperature_range = _Range()
        self._usage_range = _Range()

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

        # Hardware handles are opened on the sampling thread, the one that also
        # closes them, so wait for it to publish what it managed to open before
        # reporting. Opening is not instant: deciding whether a counter has
        # anything to read means sampling it, and PDH rate counters need an
        # interval between two collections first.
        self._ready.wait(timeout=30)
        print("\nLogging started. Metric sources:")
        for line in self._capabilities:
            print(line)
        print()

        # Power is required, so this is checked before the target program is
        # launched: better to abort with instructions than to run a whole
        # workload and hand back a CSV missing its power column.
        #
        # Temperature is deliberately *not* checked here. Plenty of machines
        # declare no ACPI thermal zone at all, and on those there is nothing
        # the user could install to fix it -- aborting would make the profiler
        # useless on hardware whose power measurement is perfectly good. The
        # capability list above has already said the column will be empty.
        if self._energy is None or not self._energy.available:
            reason = (self._energy.error if self._energy else
                      self._probe_error or "the hardware probe did not finish")
            self._abort()
            raise MetricsUnavailableError(reason)

    def _abort(self):
        """Unwind a start() that failed, leaving no half-written run behind."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        with self._lock:
            self._buffer.clear()        # also disarms the atexit flush
        for path in (self._csv_file, self._meta_file):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._csv_file = self._meta_file = None

    def _temperature_is_static(self):
        """Did the thermal zone hold one value while the CPU load moved?

        Firmware on some machines declares an ACPI thermal zone and then never
        updates it. That is indistinguishable from a cool CPU in a single
        sample, but not across a run: a zone that does not move half a degree
        while load swings tens of points is reporting a constant, not a
        temperature. Worth saying out loud, because the chart looks plausible.
        """
        return (self._temperature_range.count >= 20
                and (self._temperature_range.spread or 0) < 0.5
                and (self._usage_range.spread or 0) > 25)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        self._flush_buffer_to_csv()
        static_temperature = self._temperature_is_static()
        self._write_metadata(static_temperature)
        if self._sensor_gaps:
            print(f"[Warning] {self._sensor_gaps} sample(s) recorded no power or "
                  f"temperature -- a performance counter stopped reporting "
                  f"part-way through the run.")
        if not self._temperature_expected:
            print("\n[Note] cpu_temperature is empty for this run: this machine "
                  "declares no\n       readable ACPI thermal zone. Every other "
                  "metric, power included, is\n       unaffected. See "
                  "`profiler diagnose`.")
        if static_temperature:
            zones = ", ".join(self._thermal.zones) if self._thermal else "the zone"
            print(f"\n[Warning] cpu_temperature never moved from "
                  f"{self._temperature_range.low:.1f} C across "
                  f"{self._temperature_range.count} samples, while CPU load "
                  f"varied by {self._usage_range.spread:.0f} points.\n"
                  f"          This machine's ACPI thermal zone ({zones}) reports "
                  f"a constant, so the temperature chart carries no signal.\n"
                  f"          Windows exposes no other CPU temperature to a "
                  f"user-mode program; the on-die sensor needs a kernel driver.")
        print(f"\nLogging stopped. CSV saved to: {self._csv_file}")
        return self._csv_file

    # -------------------------------------------------------------- sampling
    def _open_hardware(self):
        try:
            self._frequency = hardware.PerCoreFrequency()
            self._energy = hardware.EnergyMeter()
            self._thermal = hardware.ThermalZone()
            self._topology = hardware.read_topology()
            self._capabilities = hardware.describe(self._frequency, self._energy,
                                                   self._thermal, self._topology)
            # Whether a temperature was ever on offer. `available` tracks a live
            # handle, so it has to be captured now, while the handle is open --
            # and a column that was never going to be filled must not be
            # counted as a sample-by-sample sensor gap.
            self._temperature_expected = bool(self._thermal
                                              and self._thermal.available)
            # psutil's first percpu call returns 0.0 for every core because it
            # has no previous sample to diff against; burn that one here.
            psutil.cpu_percent(interval=None, percpu=True)
        except Exception as exc:
            self._probe_error = f"the hardware probe failed: {exc}"
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

        temperature = self._thermal.cpu_temperature_c() if self._thermal else None
        power = self._energy.cpu_power_watts() if self._energy else None
        if power is None or (temperature is None and self._temperature_expected):
            # A source that answered at start() and has now stopped. Counted
            # only for sources that were actually available, so a machine with
            # no thermal zone does not report every sample as a gap.
            self._sensor_gaps += 1

        self._temperature_range.add(temperature)
        self._usage_range.add(cpu_usage)

        return {
            "cpu_usage": cpu_usage,
            "memory_usage": memory.percent,
            "total_memory": memory.total,
            "swap_usage": swap.percent,
            "total_swap": swap.total,
            "per_core_usage": core_usage,
            "per_core_freq": core_freq,
            "cpu_temperature": temperature,
            "cpu_power": power,
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
            # Close every PDH query on the thread that opened it, so no handle
            # outlives the sampler.
            for source in (self._frequency, self._energy, self._thermal):
                if source:
                    source.close()

    # ----------------------------------------------------------------- output
    def _flush_buffer_to_csv(self):
        with self._lock:
            # `_csv_file` is None after an aborted start(); a late sample landing
            # in the buffer must not resurrect the run at exit.
            if not self._buffer or not self._csv_file:
                return
            file_empty = (not os.path.exists(self._csv_file)
                          or os.path.getsize(self._csv_file) == 0)
            with open(self._csv_file, mode="a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._buffer[0].keys())
                if file_empty:
                    writer.writeheader()
                writer.writerows(self._buffer)
            self._buffer.clear()

    def _write_metadata(self, static_temperature=False):
        """Sidecar describing the machine and which sensors actually worked.

        Written next to the CSV with the same timestamp so `organize_logs`
        files it into the same folder. Plotting reads it to label cores
        correctly on hybrid CPUs, and to caption a temperature chart that only
        looks like data.
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
            "power_source": self._energy.source if self._energy else None,
            "power_domains": self._energy.instances if self._energy else [],
            "temperature_source": self._thermal.source if self._thermal else None,
            "temperature_zones": self._thermal.zones if self._thermal else [],
            "temperature_available": self._temperature_expected,
            "temperature_static": static_temperature,
            "sensor_lost": bool((self._energy and self._energy.lost)
                                or (self._thermal and self._thermal.lost)),
            "sensor_gap_samples": self._sensor_gaps,
        }
        try:
            with open(self._meta_file, "w") as f:
                json.dump(meta, f, indent=2)
        except OSError as exc:
            print(f"[Warning] could not write run metadata: {exc}")


if __name__ == "__main__":
    logger = SystemMetricsLogger()
    try:
        logger.start(metrics_interval_ms=500, output_dir=".", csv_write_interval_s=5)
    except MetricsUnavailableError as exc:
        raise SystemExit(f"\nCannot start: {exc}\n\n{hardware.POWER_HELP}")
    time.sleep(20)
    logger.stop()
