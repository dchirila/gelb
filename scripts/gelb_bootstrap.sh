#!/bin/bash

# Bootstrap script for GeLB development environment
# Removes existing venv, creates a new one, and installs requirements using uv

set -e  # Exit on error

echo "Setting up GeLB development environment with uv..."

# Get the root directory (parent of scripts directory)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Define venv path
VENV_PATH="$ROOT_DIR/.venv"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the current script
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Remove existing venv if it exists
if [ -d "$VENV_PATH" ]; then
    echo "Removing existing virtual environment..."
    rm -rf "$VENV_PATH"
fi

# Create new virtual environment and install dependencies
echo "Creating virtual environment and installing dependencies..."
cd "$ROOT_DIR"
uv venv
uv sync --all-extras

echo "GeLB development environment setup complete!"
echo "To activate the environment, run: source .venv/bin/activate"
