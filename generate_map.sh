#!/bin/bash
# Generate LibreNMS Weathermap - Cron-friendly script
# This script activates the virtual environment and runs the weathermap generator in headless mode

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the script directory
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Error: Virtual environment not found at $SCRIPT_DIR/.venv"
    exit 1
fi

# Run weathermap in headless mode
python main.py --no-show

# Exit with the status of the python command
exit $?
