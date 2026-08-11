"""Filing of profiler output into timestamped folders.

The `YYYYmmdd_HHMMSS` stamp in each filename is the join key across the whole
pipeline: the CSV, its JSON sidecar and every PNG share one stamp, and that is
what groups them into a single run folder.
"""
import os
import re
import shutil

_STAMPED = re.compile(r"_(\d{8}_\d{6})\.(png|csv|json)$")


def organize_logs(base_dir="."):
    """Move every stamped artefact in `base_dir` into `logs/<timestamp>/`."""
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    grouped = {}
    for fname in os.listdir(base_dir):
        match = _STAMPED.search(fname)
        if match:
            grouped.setdefault(match.group(1), []).append(fname)

    if not grouped:
        print(f"No timestamped output found in {base_dir}; nothing to organize.")
        return []

    moved = []
    for timestamp, files in grouped.items():
        target_dir = os.path.join(logs_dir, timestamp)
        os.makedirs(target_dir, exist_ok=True)
        for fname in files:
            src = os.path.join(base_dir, fname)
            dst = os.path.join(target_dir, fname)
            if os.path.exists(dst):
                os.remove(dst)      # shutil.move refuses to clobber on Windows
            shutil.move(src, dst)
        moved.append(target_dir)
        print(f"Organized {len(files)} file(s) into {target_dir}")

    return moved
