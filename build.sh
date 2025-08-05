#!/usr/bin/env bash
# exit on error
set -o errexit

# Ensure we're using Python 3.11
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [ "$PYTHON_VERSION" != "3.11" ]; then
    echo "Error: Required Python 3.11 but found Python $PYTHON_VERSION"
    exit 1
fi

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
