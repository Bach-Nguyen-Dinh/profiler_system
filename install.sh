#!/usr/bin/env bash
set -euo pipefail

INSTALL_NAME="profiler"
INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER="$SCRIPT_DIR/analyzer.py"
WRAPPER="$INSTALL_DIR/$INSTALL_NAME"

# Verify analyzer.py exists
if [[ ! -f "$ANALYZER" ]]; then
    echo "Error: analyzer.py not found at $ANALYZER"
    exit 1
fi

# Check for required Python packages
echo "Checking Python dependencies..."
python3 - <<'EOF'
import importlib, sys
missing = []
for pkg in ["psutil", "matplotlib", "networkx", "pyvis", "pandas"]:
    if importlib.util.find_spec(pkg) is None:
        missing.append(pkg)
if missing:
    print(f"Missing packages: {', '.join(missing)}")
    print(f"Install with: pip3 install {' '.join(missing)}")
    sys.exit(1)
else:
    print("All required packages found.")
EOF

# Write the wrapper script
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
exec python3 "$ANALYZER" "\$@"
EOF

chmod +x "$WRAPPER"

echo ""
echo "Installed: $WRAPPER"
echo ""
echo "Usage:"
echo "  $INSTALL_NAME <target_script.py> [profiler_options] -- [target_script_args]"
echo "  sudo $INSTALL_NAME allow_cpu_power_metric_capture   # one-time RAPL setup"
