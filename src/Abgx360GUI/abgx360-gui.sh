#!/bin/bash
# Launch abgx360 GUI on Linux/macOS from a source checkout.
# On first run, create the bundled virtual environment and
# install the app's deps; the app itself then downloads and
# builds the abgx360 engine into ~/.local/share/abgx360-gui.
cd "$(dirname "$(readlink -f "$0")")"
if [ ! -x .venv/bin/python ]; then
    echo "First run: setting up the Python environment..."
    python3 -m venv .venv || {
        echo "Could not create the environment. Install Python 3.10+ and retry."
        exit 1
    }
fi
if ! .venv/bin/python -c "import PySide6" 2>/dev/null; then
    echo "Installing Python dependencies..."
    .venv/bin/python -m pip install -r requirements.txt || {
        echo "Dependency install failed - check connection, re-run."
        exit 1
    }
fi
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/abgx360-gui"
export ABGX360_GUI_DATA_DIR="$DATA"
export ABGX360_GUI_ENGINE_DIR="$DATA/engine"
exec .venv/bin/python app/main.py "$@"
