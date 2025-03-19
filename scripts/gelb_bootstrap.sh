#!/bin/bash

# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements

set -e  # Exit on error

echo "Setting up GeLB development environment..."

# Get the root directory (parent of scripts directory)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Define venv path
VENV_PATH="$ROOT_DIR/venv"

# Remove existing venv if it exists
if [ -d "$VENV_PATH" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$VENV_PATH"
fi

# Create new virtual environment
echo "Creating new virtual environment..."
python3 -m venv "$VENV_PATH"

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install requirements
REQUIREMENTS_PATH="$ROOT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_PATH" ]; then
    echo "Installing requirements..."
    pip install -r "$REQUIREMENTS_PATH"
else
    echo "Warning: requirements.txt not found at $REQUIREMENTS_PATH"
    exit 1
fi

echo "GeLB development environment setup complete!"
