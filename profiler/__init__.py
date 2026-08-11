"""Windows system profiler.

Samples system-wide CPU, memory, frequency, power and temperature while a
target script runs as a subprocess, then charts the result.

This package is the Windows implementation; the Linux build lives on the `dev`
branch and reads the same metrics out of sysfs.
"""
from .logs import organize_logs
from .metrics import SystemMetricsLogger
from .plotting import plot_system_metrics

__all__ = ["SystemMetricsLogger", "plot_system_metrics", "organize_logs"]
