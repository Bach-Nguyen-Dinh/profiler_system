#!/usr/bin/env bash
set -euo pipefail

INSTALL_NAME="profiler"
INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER="$SCRIPT_DIR/analyzer.py"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
WRAPPER="$INSTALL_DIR/$INSTALL_NAME"

# Verify analyzer.py exists
if [[ ! -f "$ANALYZER" ]]; then
    echo "Error: analyzer.py not found at $ANALYZER"
    exit 1
fi

# Locate uv. When run under sudo, root's PATH usually misses ~/.local/bin, so
# fall back to the invoking user's install before giving up.
UV="$(command -v uv || true)"
if [[ -z "$UV" && -n "${SUDO_USER:-}" ]]; then
    for candidate in "$(getent passwd "$SUDO_USER" | cut -d: -f6)/.local/bin/uv" "/usr/local/bin/uv"; do
        if [[ -x "$candidate" ]]; then
            UV="$candidate"
            break
        fi
    done
fi

if [[ -z "$UV" ]]; then
    echo "Error: uv not found."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create/refresh the project virtual environment from pyproject.toml + uv.lock.
# uv downloads the pinned Python (.python-version) if it is not already present.
echo "Syncing virtual environment with uv..."
if [[ -n "${SUDO_USER:-}" ]]; then
    # Keep .venv owned by the real user, not root.
    sudo -u "$SUDO_USER" "$UV" sync --project "$SCRIPT_DIR"
else
    "$UV" sync --project "$SCRIPT_DIR"
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Error: expected virtual environment at $SCRIPT_DIR/.venv but none was created."
    exit 1
fi

# Write the wrapper script.
#
# The wrapper calls the venv interpreter directly rather than activating the
# venv, so PATH is left alone and the profiled target script still runs under
# the user's own "python3" with its own dependencies.
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
exec "$VENV_PYTHON" "$ANALYZER" "\$@"
EOF

chmod +x "$WRAPPER"

echo ""
echo "Installed: $WRAPPER"
echo "Using:     $VENV_PYTHON"
echo ""
echo "Usage:"
echo "  $INSTALL_NAME <target_script.py> [profiler_options] -- [target_script_args]"
echo "  sudo $INSTALL_NAME allow_cpu_power_metric_capture   # one-time RAPL setup"
