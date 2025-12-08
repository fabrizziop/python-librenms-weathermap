#!/bin/bash
# LibreNMS Weathermap Setup Script

set -e

echo "=== LibreNMS Weathermap Setup ==="
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.11"

if (( $(echo "$PYTHON_VERSION < $REQUIRED_VERSION" | bc -l) )); then
    echo "⚠️  Warning: Python $PYTHON_VERSION detected. Python 3.11+ recommended."
else
    echo "✓ Python $PYTHON_VERSION detected"
fi

# Create virtual environment
echo
echo "Creating virtual environment..."
python3 -m venv .venv

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo
echo "=== Setup Complete ==="
echo
echo "To activate the virtual environment:"
echo "  source .venv/bin/activate"
echo
echo "To run the editor:"
echo "  python editor.py"
echo
echo "To generate a weathermap:"
echo "  python main.py"
echo
echo "Don't forget to configure config.ini with your LibreNMS details!"
