"""Profile a Python script on Windows.

Runs the target as a subprocess while a background thread samples system-wide
metrics, then charts the CSV and files everything into a timestamped folder.

    python analyzer.py <target_script.py> [options] -- [target args]
    python analyzer.py diagnose
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime

from profiler import (MetricsUnavailableError, SystemMetricsLogger,
                      organize_logs, plot_system_metrics)

# Power, temperature, frequency and topology all come from Windows itself
# through ctypes, so nothing here is a sensor dependency -- these are only the
# sampling and charting libraries.
REQUIRED_PACKAGES = ["psutil", "pandas", "matplotlib", "numpy"]

# install.ps1 drops this beside the interpreter of the private environment it
# creates. Its presence is what distinguishes "the profiler owns this
# interpreter" from "the user happens to be running us from their own venv".
VENV_MARKER = ".profiler-venv"


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


def _running_in_profiler_venv():
    return os.path.isfile(os.path.join(sys.prefix, VENV_MARKER))


def _real_executable(candidate):
    """The interpreter `candidate` actually launches, or None.

    Asking it is the check. It resolves a launcher to what it launches, and it
    is what rejects the Microsoft Store python.exe alias stub, which produces
    no output and a non-zero status instead of running anything.
    """
    try:
        result = subprocess.run([candidate, "-c", "import sys; print(sys.executable)"],
                                capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    path = result.stdout.strip()
    if result.returncode != 0 or not path or not os.path.isfile(path):
        return None
    return path


def resolve_target_python(explicit=None):
    """Which interpreter runs the profiled script.

    Deliberately not always `sys.executable`. When the profiler was installed
    into its own environment, its interpreter has only psutil/pandas/
    matplotlib/numpy in it -- handing that to a target script would hide the
    script's own dependencies and report the failure as the user's bug. So:

      1. --python, if given,
      2. the `python` on PATH, when we are running from the private
         environment. An activated virtualenv puts itself first on PATH, so
         this picks up the user's project without being told about it,
      3. sys.executable otherwise -- `python analyzer.py foo.py` behaves
         exactly as it always has, target and profiler sharing an interpreter.
    """
    if explicit:
        resolved = _real_executable(explicit)
        if not resolved:
            sys.exit(f"--python: not a working Python interpreter: {explicit}")
        return resolved

    if _running_in_profiler_venv():
        found = shutil.which("python") or shutil.which("py")
        resolved = _real_executable(found) if found else None
        if resolved and not os.path.isfile(os.path.join(
                os.path.dirname(os.path.dirname(resolved)), VENV_MARKER)):
            return resolved
        # Nothing else on PATH, so the target has to share our interpreter.
        # Say so: a target that then fails on a missing import needs to know
        # which environment it was looking in.
        print("[Note] no separate Python found on PATH; the target will run in the\n"
              "       profiler's own environment, which has only its own packages.\n"
              "       Pass --python <path-to-python.exe> to choose one.")

    return sys.executable


def analyze_workflow(main_program, program_args=None, metrics_interval_ms=500,
                     output_dir=None, csv_write_interval_s=5, target_python=None):
    program_args = list(program_args or [])
    # argparse leaves the "--" separator in place; the target should not see it.
    if program_args and program_args[0] == "--":
        program_args = program_args[1:]

    if not os.path.isfile(main_program):
        sys.exit(f"Target script not found: {main_program}")

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(main_program))
    os.makedirs(output_dir, exist_ok=True)

    # Resolved before start(), so a bad --python fails here rather than after
    # the counters are open and a half-written run is already on disk.
    target_python = resolve_target_python(target_python)

    _log_step(f"Starting workflow for {main_program}")
    _log_step("Starting metrics logging...")
    logger = SystemMetricsLogger()
    # Which interpreter ran the workload is part of the run's provenance, so it
    # goes in the sidecar next to the machine description.
    logger.target_python = target_python
    try:
        logger.start(metrics_interval_ms, output_dir, csv_write_interval_s)
    except MetricsUnavailableError as exc:
        # Only power gets here. Refuse to profile at all rather than run the
        # whole workload and hand back a CSV with an empty power column.
        from profiler import hardware

        sys.exit(f"\nCannot start: {exc}\n\n{hardware.POWER_HELP}")

    try:
        # A resolved interpreter path, never "python3": that name does not
        # exist on a default Windows install. See resolve_target_python for
        # why this is not simply sys.executable.
        cmd = [target_python, os.path.abspath(main_program)] + program_args
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
    parser.add_argument("--python", default=None, dest="target_python",
                        help="interpreter to run the target with "
                             "(default: the `python` on PATH, or this one)")

    args, program_args = parser.parse_known_args()

    _check_packages()
    analyze_workflow(args.main_program, program_args, args.metrics_interval_ms,
                     args.output_dir, args.csv_write_interval_s,
                     args.target_python)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
