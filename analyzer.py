"""Profile a Python script on Windows.

Runs the target as a subprocess while a background thread samples system-wide
metrics, then charts the CSV and files everything into a timestamped folder.

    python analyzer.py <target_script.py> [options] -- [target args]
    python analyzer.py diagnose
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime

from profiler import (MetricsUnavailableError, SystemMetricsLogger,
                      organize_logs, plot_system_metrics)

# Power, temperature, frequency and topology all come from Windows itself
# through ctypes, so nothing here is a sensor dependency -- these are only the
# sampling and charting libraries.
REQUIRED_PACKAGES = ["psutil", "pandas", "matplotlib", "numpy"]


def _log_step(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def _require_windows():
    if os.name != "nt":
        sys.exit(
            "This branch (dev_windows) is the Windows-only build of the profiler.\n"
            "On Linux, use the `dev` branch, which reads metrics from sysfs.")


def _check_packages():
    import importlib.util

    missing = [p for p in REQUIRED_PACKAGES if importlib.util.find_spec(p) is None]
    if missing:
        sys.exit(f"Missing required packages: {', '.join(missing)}\n"
                 f"Run Install-Profiler.cmd, or install them with:\n"
                 f"  {sys.executable} -m pip install {' '.join(missing)}")


def analyze_workflow(main_program, program_args=None, metrics_interval_ms=500,
                     output_dir=None, csv_write_interval_s=5):
    program_args = list(program_args or [])
    # argparse leaves the "--" separator in place; the target should not see it.
    if program_args and program_args[0] == "--":
        program_args = program_args[1:]

    if not os.path.isfile(main_program):
        sys.exit(f"Target script not found: {main_program}")

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(main_program))
    os.makedirs(output_dir, exist_ok=True)

    _log_step(f"Starting workflow for {main_program}")
    _log_step("Starting metrics logging...")
    logger = SystemMetricsLogger()
    try:
        logger.start(metrics_interval_ms, output_dir, csv_write_interval_s)
    except MetricsUnavailableError as exc:
        # Only power gets here. Refuse to profile at all rather than run the
        # whole workload and hand back a CSV with an empty power column.
        from profiler import hardware

        sys.exit(f"\nCannot start: {exc}\n\n{hardware.POWER_HELP}")

    try:
        # sys.executable, never "python3": that name does not exist on a default
        # Windows install, and this way the target inherits our virtualenv.
        cmd = [sys.executable, os.path.abspath(main_program)] + program_args
        _log_step(f"Running: {subprocess.list2cmdline(cmd)}")
        subprocess.run(cmd, check=True)
        _log_step("Target program finished")
    except KeyboardInterrupt:
        _log_step("Interrupted; keeping metrics collected so far")
    except subprocess.CalledProcessError as exc:
        print(f"Target exited with status {exc.returncode}")
    finally:
        # Always land the output, even after a crash or Ctrl+C.
        _log_step("Stopping metrics logging...")
        out_file = logger.stop()

        _log_step("Plotting system metrics...")
        try:
            plot_system_metrics(input_filename=out_file, output_dir=output_dir)
        except Exception as exc:
            print(f"[Warning] plotting failed: {exc}")

        _log_step("Organizing logs...")
        organize_logs(output_dir)
        _log_step("Workflow complete")


def diagnose():
    """Report which metric sources this machine can supply.

    Exits non-zero only when CPU power is missing, the one metric a run cannot
    go ahead without, so the installer can use this as its final verification
    step. A missing temperature is printed but does not fail the check.
    """
    from profiler import hardware

    print("Profiler capability check\n" + "=" * 40)
    frequency = hardware.PerCoreFrequency()
    energy = hardware.EnergyMeter()
    thermal = hardware.ThermalZone()
    topology = hardware.read_topology()
    for line in hardware.describe(frequency, energy, thermal, topology):
        print(line)

    # Read the verdicts before closing: `available` reflects a live handle.
    power_ok, temperature_ok = energy.available, thermal.available
    for source in (frequency, energy, thermal):
        source.close()

    if not power_ok:
        print("\n" + hardware.POWER_HELP)
        sys.exit(1)

    # Missing temperature is reported but not fatal: a machine that declares no
    # thermal zone still profiles, so this must not fail the installer's check.
    if not temperature_ok:
        print("\n" + hardware.TEMPERATURE_HELP)
        print("\nCPU power is available; runs will go ahead without a temperature.")
        sys.exit(0)

    print("\nAll metric sources are available.")
    print("Note: the temperature is a firmware-reported ACPI zone, not the CPU's\n"
          "on-die sensor. Some machines report a constant there; a run that sees\n"
          "one says so when it finishes.")
    sys.exit(0)


def main():
    _require_windows()

    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        diagnose()

    parser = argparse.ArgumentParser(
        description="Profile a Python script while sampling system metrics.",
        epilog="Everything after -- is forwarded to the target script.")
    parser.add_argument("main_program", help="path to the Python script to profile")
    parser.add_argument("--metrics_interval_ms", type=int, default=500,
                        help="sampling interval in milliseconds (default 500)")
    parser.add_argument("--output_dir", default=None,
                        help="output directory (default: the target's directory)")
    parser.add_argument("--csv_write_interval_s", type=int, default=5,
                        help="how often to flush samples to the CSV (default 5)")

    args, program_args = parser.parse_known_args()

    _check_packages()
    analyze_workflow(args.main_program, program_args, args.metrics_interval_ms,
                     args.output_dir, args.csv_write_interval_s)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
