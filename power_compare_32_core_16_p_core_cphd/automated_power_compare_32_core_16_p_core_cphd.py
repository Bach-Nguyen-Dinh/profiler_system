#!/usr/bin/env python3
"""Automate a 32-core vs 16-P-core CPU-power comparison over the CPHD AIC pipeline.

For each round it:
  1. turns ALL E-cores online  -> 32 cores            (run A, plotted blue)
  2. profiles cphd_aic.py on the given CPHD file
  3. copies that run's latest logs/<ts>/ folder into the round's testNN/
  4. turns ALL E-cores offline -> 16 P-cores          (run B, plotted red)
  5. profiles cphd_aic.py again
  6. copies that run's latest logs/<ts>/ folder into testNN/
  7. lifts each log folder's CSV up into testNN/ (so 2 CSVs sit side by side)
  8. runs plotting_power_compare.py on testNN/ (once plain, once labelled)

Everything for a run of N rounds lands under:
  power_compare_32_core_16_p_core_cphd/<CPHD>_<YYMMDD_HHMMSS>/test01 ... testNN

Because the E-core on/off scripts use `sudo tee`, launch this whole program
under sudo so those inner sudo calls are already authorized:

  sudo python3 automated_power_compare_32_core_16_p_core_cphd.py \
       --file 2023-10-22-15-20-28_CPHD --round 5
"""

import argparse
import datetime
import glob
import os
import pwd
import shutil
import subprocess
import sys

# --- Fixed environment layout -------------------------------------------------
# This program lives alongside plotting_power_compare.py and the E-core on/off
# scripts, so those (and the output) are resolved relative to this file.
# analyzer.py stayed in profiler_system/, so it keeps an absolute path.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILER_SYSTEM = "/home/sarthak/profiler_system"
WORKSPACE = "/home/sarthak/workspace"
SAR_DIR = os.path.join(WORKSPACE, "SAR_codebase")
LOGS_DIR = os.path.join(SAR_DIR, "logs")
ANALYZER = os.path.join(PROFILER_SYSTEM, "analyzer.py")
PLOTTING = os.path.join(SCRIPT_DIR, "plotting_power_compare.py")
COMPARE_ROOT = SCRIPT_DIR

# The turn-on script's filename really does contain a comma; the turn-off one a dot.
TURN_ON_SCRIPT = os.path.join(SCRIPT_DIR, "turn_on_all_e_core.sh")
TURN_OFF_SCRIPT = os.path.join(SCRIPT_DIR, "turn_off_all_e_core.sh")


def run(cmd, cwd=None):
    """Run a command, echoing it, and abort the whole automation if it fails."""
    printable = " ".join(cmd)
    print(f"\n$ {printable}" + (f"   (cwd={cwd})" if cwd else ""))
    subprocess.run(cmd, cwd=cwd, check=True)


def list_log_dirs():
    """Set of timestamped subfolder names currently under SAR_codebase/logs."""
    if not os.path.isdir(LOGS_DIR):
        return set()
    return {
        name for name in os.listdir(LOGS_DIR)
        if os.path.isdir(os.path.join(LOGS_DIR, name))
    }


def profile_run(cphd_file):
    """Run the profiler on cphd_aic.py and return the path of the log folder it created.

    We snapshot the log folders before the run and diff afterwards so we pick up
    exactly the folder this run produced, regardless of clock skew or naming.
    """
    before = list_log_dirs()
    run(
        [
            sys.executable, ANALYZER, "cphd_aic.py",
            "--metrics_interval_ms", "500",
            "--csv_write_interval_s", "5",
            "--", "--file", f"{cphd_file}.cphd",
        ],
        cwd=SAR_DIR,
    )
    new = list_log_dirs() - before
    if not new:
        raise SystemExit(
            f"No new log folder appeared under {LOGS_DIR} after the profiler run."
        )
    # If more than one appeared (shouldn't happen), take the newest by name.
    newest = sorted(new)[-1]
    return os.path.join(LOGS_DIR, newest)


def copy_log_into(test_dir, log_folder):
    """Copy a whole log folder into test_dir and lift its CSV up to test_dir/."""
    dst = os.path.join(test_dir, os.path.basename(log_folder))
    shutil.copytree(log_folder, dst)
    print(f"  copied log folder -> {dst}")
    for csv in glob.glob(os.path.join(dst, "*.csv")):
        shutil.copy2(csv, os.path.join(test_dir, os.path.basename(csv)))
        print(f"  lifted CSV       -> {os.path.join(test_dir, os.path.basename(csv))}")


def one_round(test_dir, cphd_file, blue_label, red_label):
    os.makedirs(test_dir, exist_ok=True)

    # Run A: all E-cores ON -> 32 cores (blue, plotted first because it sorts first)
    run(["bash", TURN_ON_SCRIPT])
    log_a = profile_run(cphd_file)
    copy_log_into(test_dir, log_a)

    # Run B: all E-cores OFF -> 16 P-cores (red)
    run(["bash", TURN_OFF_SCRIPT])
    log_b = profile_run(cphd_file)
    copy_log_into(test_dir, log_b)

    # Comparison plot: once plain (to see which line is which colour), once labelled.
    run([sys.executable, PLOTTING, test_dir])
    run([sys.executable, PLOTTING, test_dir, "--blue", blue_label, "--red", red_label])


def restore_ownership(path):
    """Best-effort: hand root-created files back to the invoking user (sudo)."""
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user or os.geteuid() != 0:
        return
    try:
        pw = pwd.getpwnam(sudo_user)
    except KeyError:
        return
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                os.chown(os.path.join(root, name), pw.pw_uid, pw.pw_gid)
            except OSError:
                pass
    try:
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Automated 32-core vs 16-P-core CPU-power comparison over the CPHD AIC pipeline."
    )
    parser.add_argument("--file", required=True,
                        help="CPHD file name WITHOUT the .cphd extension, "
                             "e.g. 2023-10-22-15-20-28_CPHD")
    parser.add_argument("--round", type=int, required=True,
                        help="Number of comparison rounds to run (test01 .. testNN).")
    parser.add_argument("--blue", default="32 cores",
                        help="Label for the 32-core (E-cores on) run. Default: '32 cores'.")
    parser.add_argument("--red", default="16 P-cores",
                        help="Label for the 16-P-core (E-cores off) run. Default: '16 P-cores'.")
    args = parser.parse_args()

    if args.round < 1:
        raise SystemExit("--round must be >= 1")

    # Accept the name with or without a trailing ".cphd" so we never double it.
    # The bare name is used for the output folder; ".cphd" is appended for the
    # profiler call inside profile_run().
    cphd_name = args.file
    if cphd_name.endswith(".cphd"):
        cphd_name = cphd_name[: -len(".cphd")]
    args.file = cphd_name

    # Sanity-check the environment before doing anything expensive.
    for path, what in [
        (ANALYZER, "profiler analyzer.py"),
        (PLOTTING, "plotting_power_compare.py"),
        (SAR_DIR, "SAR_codebase directory"),
        (TURN_ON_SCRIPT, "turn-on E-core script"),
        (TURN_OFF_SCRIPT, "turn-off E-core script"),
    ]:
        if not os.path.exists(path):
            raise SystemExit(f"Required {what} not found at: {path}")

    if os.geteuid() != 0:
        print(
            "WARNING: not running as root. The E-core on/off scripts use `sudo tee` "
            "and may prompt for a password (and could stall between rounds). "
            "Re-run with `sudo` for unattended operation.",
            file=sys.stderr,
        )

    stamp = datetime.datetime.now().strftime("%y%m%d_%H%M%S")
    final_dir = os.path.join(COMPARE_ROOT, f"{args.file}_{stamp}")
    os.makedirs(final_dir, exist_ok=True)
    print(f"Output folder: {final_dir}")

    for r in range(1, args.round + 1):
        test_dir = os.path.join(final_dir, f"test{r:02d}")
        print(f"\n{'=' * 70}\nROUND {r}/{args.round}  ->  {test_dir}\n{'=' * 70}")
        one_round(test_dir, args.file, args.blue, args.red)

    restore_ownership(final_dir)
    print(f"\nDone. All {args.round} round(s) under: {final_dir}")


if __name__ == "__main__":
    main()
