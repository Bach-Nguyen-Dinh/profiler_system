import os
import system_metrics as system_metrics
import plotting
import code_dependencies_analyser
import re
import shutil
import sys
import importlib.util
import argparse

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
def analyze_workflow(main_function, program_args=None, metrics_interval_ms=500, output_dir=".", csv_write_interval_s=5):
    if program_args is None:
        program_args = []

    # Get base filename
    current_file = os.path.basename(main_function)

    # # Get current file name of the main script from the main_function
    # current_file = os.path.basename(main_function.__code__.co_filename)

    # Analyse code dependencies in the specified directory
    code_dependencies_analyser.analyse_dependencies(os.getcwd(), 'py', current_file)

    # Start system metrics logging
    logger = system_metrics.SystemMetricsLogger()
    # Start logging metrics every 500 ms by default, write to CSV every 5 seconds by default
    logger.start(metrics_interval_ms, output_dir, csv_write_interval_s)

    # # Run the main function
    # main_function()

    # Dynamically import and run the main program
    # Backup current argv
    original_argv = sys.argv.copy()
    # Reset argv so cpu.py sees only its own name (no analyzer.py args)
    sys.argv = [main_function] + program_args

    try:
        module = load_module_from_path(main_function)
        # If the module has a function named main(), call it
        if hasattr(module, "main") and callable(module.main):
            module.main()
        else:
            print(f"Running {main_function} directly (no main() found)...")
    finally:
        # Restore argv after import
        sys.argv = original_argv

    # Finalize logging
    out_file = logger.stop()

    out_file = os.path.basename(out_file)
    out_file = out_file.lstrip("./")
    # Plot the system metrics from the generated CSV file
    plotting.plot_system_metrics(input_filename=out_file)

    # Organize logs into timestamped folders
    organize_logs(".")

def main():
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

    # # Check that main_program was provided
    # if len(sys.argv) < 2:
    #     print("Usage: python3 my_app.py <main_program> [metrics_interval_ms] [output_dir] [csv_write_interval_s]")
    #     sys.exit(1)

    # main_program = sys.argv[1]
    # metrics_interval_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    # output_dir = sys.argv[3] if len(sys.argv) > 3 else "."
    # csv_write_interval_s = int(sys.argv[4]) if len(sys.argv) > 4 else 5

    # analyze_workflow(main_program, metrics_interval_ms, output_dir, csv_write_interval_s)

if __name__ == "__main__":
    main()



