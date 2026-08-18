#!/usr/bin/env bash
set -euo pipefail

INSTALL_NAME="profiler"
INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER="$SCRIPT_DIR/analyzer.py"
VENV_DIR="$SCRIPT_DIR/.venv"
WRAPPER="$INSTALL_DIR/$INSTALL_NAME"
UDEV_RULE_FILE="/etc/udev/rules.d/99-rapl.rules"

REMOVE_VENV=0
REMOVE_RAPL=0
FORCE=0

usage() {
    cat <<USAGE
Usage: sudo bash uninstall.sh [options]

Removes what install.sh created. By default only the $WRAPPER
wrapper is removed; the venv and the RAPL udev rule are left alone.

Options:
  --venv     also delete $VENV_DIR (recreate later with "uv sync")
  --rapl     also remove the RAPL udev rule at $UDEV_RULE_FILE,
             undoing "profiler allow_cpu_power_metric_capture"
  --all      --venv and --rapl together
  --force    remove $WRAPPER even if it does not point at this repo
  -h, --help show this message
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --venv)  REMOVE_VENV=1 ;;
        --rapl)  REMOVE_RAPL=1 ;;
        --all)   REMOVE_VENV=1; REMOVE_RAPL=1 ;;
        --force) FORCE=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Error: unknown option '$1'"; echo ""; usage; exit 1 ;;
    esac
    shift
done

if [[ $EUID -ne 0 ]]; then
    echo "Error: this script must be run with sudo (it writes under $INSTALL_DIR)."
    echo "Usage: sudo bash uninstall.sh [--venv] [--rapl] [--all]"
    exit 1
fi

# --- wrapper ---------------------------------------------------------------
if [[ -e "$WRAPPER" ]]; then
    # Only delete a wrapper that actually points at this checkout, so an
    # unrelated "profiler" binary from somewhere else is never clobbered.
    if grep -qF "$ANALYZER" "$WRAPPER" 2>/dev/null || [[ $FORCE -eq 1 ]]; then
        rm -f "$WRAPPER"
        echo "Removed:   $WRAPPER"
    else
        echo "Skipped:   $WRAPPER does not reference $ANALYZER."
        echo "           It was installed by something else; re-run with --force to remove it anyway."
    fi
else
    echo "Not found: $WRAPPER (nothing to remove)"
fi

# --- virtual environment ---------------------------------------------------
if [[ $REMOVE_VENV -eq 1 ]]; then
    if [[ -d "$VENV_DIR" ]]; then
        rm -rf "$VENV_DIR"
        echo "Removed:   $VENV_DIR"
    else
        echo "Not found: $VENV_DIR (nothing to remove)"
    fi
fi

# --- RAPL udev rule --------------------------------------------------------
if [[ $REMOVE_RAPL -eq 1 ]]; then
    if [[ -e "$UDEV_RULE_FILE" ]]; then
        rm -f "$UDEV_RULE_FILE"
        echo "Removed:   $UDEV_RULE_FILE"
        udevadm control --reload-rules
        udevadm trigger
        echo "Reloaded:  udev rules"
        echo "           Existing RAPL file permissions stay as they are until the next reboot."
    else
        echo "Not found: $UDEV_RULE_FILE (nothing to remove)"
    fi
fi

echo ""
echo "Uninstall complete."
if [[ $REMOVE_VENV -eq 0 || $REMOVE_RAPL -eq 0 ]]; then
    echo "Left in place:"
    if [[ $REMOVE_VENV -eq 0 ]]; then
        echo "  $VENV_DIR (remove with --venv)"
    fi
    if [[ $REMOVE_RAPL -eq 0 ]]; then
        echo "  $UDEV_RULE_FILE, if present (remove with --rapl)"
    fi
fi
