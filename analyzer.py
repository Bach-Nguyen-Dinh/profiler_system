import os
import system_metrics as system_metrics
import plotting
import code_dependencies_analyser
import re
import shutil
import sys
import importlib.util
import argparse
import subprocess

# Organize logs into timestamped folders
def organize_logs(base_dir="."):
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Regex to capture timestamps like _20250910_122351
    pattern = re.compile(r"_(\d{8}_\d{6})\.(png|csv)$")

    grouped_files = {}

    # Find matching files
    for fname in os.listdir(base_dir):
        match = pattern.search(fname)
        if match:
            timestamp = match.group(1)
            grouped_files.setdefault(timestamp, []).append(fname)

    # Move files into timestamped folders
    for timestamp, files in grouped_files.items():
        target_dir = os.path.join(logs_dir, timestamp)
        os.makedirs(target_dir, exist_ok=True)

        for f in files:
            src = os.path.join(base_dir, f)
            dst = os.path.join(target_dir, f)
            shutil.move(src, dst)

    print(f"\nOrganized logs into {logs_dir}/{timestamp}/")

# Dynamically load a .py file
def load_module_from_path(path):
    spec = importlib.util.spec_from_file_location("user_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# take in the main function to analyze its dependencies
def analyze_workflow(main_program, program_args=None, metrics_interval_ms=500, output_dir=".", csv_write_interval_s=5):
    if program_args is None:
        program_args = []

    current_file = os.path.basename(main_program)

    # Analyze dependencies
    code_dependencies_analyser.analyse_dependencies(os.getcwd(), 'py', current_file)

    # Start metrics logging
    logger = system_metrics.SystemMetricsLogger()
    logger.start(metrics_interval_ms, output_dir, csv_write_interval_s)

    try:
        # Run the main program as a subprocess
        # Remove stray '--' at the beginning of program_args (if any)
        if len(program_args) > 0 and program_args[0] == "--":
            program_args = program_args[1:]
        cmd = ["python3", main_program] + program_args

        print(f"\nRunning: {' '.join(cmd)}\n")
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as e:
        print(f"Error running {main_program}: {e}")
    finally:
        # Stop logging
        out_file = logger.stop()
        out_file = os.path.basename(out_file).lstrip("./")

        # Plot the system metrics from the generated CSV file
        plotting.plot_system_metrics(input_filename=out_file)

        # Organize logsinto timestamped folders
        organize_logs(".")


def setup_cpu_power_metrics():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_rapl_permissions.sh")
    if not os.path.exists(script):
        print("Error: setup script not found.")
        sys.exit(1)
    if os.geteuid() != 0:
        print("This command must be run with sudo:")
        print("  sudo python3 profiler_system/analyzer.py allow_cpu_power_metric_capture")
        sys.exit(1)

    print("Setting up CPU power metric capture...")
    result = subprocess.run(
        ["bash", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        print("CPU power metric capture enabled. You can now run the profiler normally.")
    else:
        print("Setup failed. You may need to check that your CPU supports Intel RAPL.")
    sys.exit(result.returncode)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "allow_cpu_power_metric_capture":
        setup_cpu_power_metrics()

    parser = argparse.ArgumentParser(description="Analyzer wrapper for Python programs.")
    parser.add_argument("main_program", help="Path to the main Python script to analyze")
    parser.add_argument("--metrics_interval_ms", type=int, default=500)
    parser.add_argument("--output_dir", default=".")
    parser.add_argument("--csv_write_interval_s", type=int, default=5)

    # Everything after "--" goes to the main program
    args, program_args = parser.parse_known_args()

    analyze_workflow(
        args.main_program,
        program_args,
        args.metrics_interval_ms,
        args.output_dir,
        args.csv_write_interval_s
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass



