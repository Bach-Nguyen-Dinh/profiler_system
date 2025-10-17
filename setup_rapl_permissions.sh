#!/bin/bash

# setup_rapl_permissions.sh
# One-time setup script to allow reading Intel RAPL energy files

set -e  # Exit on error

UDEV_RULE_FILE="/etc/udev/rules.d/99-rapl.rules"
RAPL_PATH="/sys/class/powercap/intel-rapl:0/energy_uj"

echo "=========================================="
echo "  RAPL Energy Monitoring Setup"
echo "=========================================="
echo ""

# Check if running as root/sudo
if [ "$EUID" -ne 0 ]; then 
    echo "Error: This script must be run with sudo"
    echo "Usage: sudo $0"
    exit 1
fi

# Check if RAPL files exist
if [ ! -e "$RAPL_PATH" ]; then
    echo "Warning: RAPL energy file not found at $RAPL_PATH"
    echo "Your CPU may not support Intel RAPL, or the intel_rapl module is not loaded."
    echo ""
    read -p "Continue anyway? [y/N]: " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "[1/3] Creating udev rule at $UDEV_RULE_FILE..."
cat > "$UDEV_RULE_FILE" << 'EOF'
# Allow read access to Intel RAPL energy monitoring
SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", ACTION=="add", RUN+="/bin/chmod -R a+r /sys/class/powercap/intel-rapl:*"
EOF

if [ $? -eq 0 ]; then
    echo "      ✓ Udev rule created successfully"
else
    echo "      ✗ Failed to create udev rule"
    exit 1
fi

echo "[2/3] Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger
echo "      ✓ Udev rules reloaded"

echo "[3/3] Applying permissions for current session..."
if [ -e "/sys/class/powercap/intel-rapl:0" ]; then
    chmod -R a+r /sys/class/powercap/intel-rapl:*
    echo "      ✓ Permissions applied"
else
    echo "      ! RAPL directory not found, permissions will apply on next boot"
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "RAPL energy files are now readable without sudo."
echo "These permissions will persist across reboots."
echo ""
echo "You can now run your Python script normally:"
echo "  python3 system_metrics.py"
echo ""
