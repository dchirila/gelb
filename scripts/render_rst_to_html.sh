#!/bin/bash

# Script to run the RST to HTML renderer

# Get the directory of this script and the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if the virtual environment exists
VENV_PATH="$PROJECT_ROOT/venv"
VENV_ACTIVATE="$VENV_PATH/bin/activate"

if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "\033[0;31mVirtual environment not found. Please run gelb_bootstrap.sh first.\033[0m"
    exit 1
fi

# Activate the virtual environment
echo "\033[0;36mActivating virtual environment...\033[0m"
source "$VENV_ACTIVATE"

# Run the RST to HTML renderer script
RENDER_SCRIPT="$SCRIPT_DIR/render_rst_to_html.py"
echo "\033[0;32mStarting RST to HTML renderer...\033[0m"
python "$RENDER_SCRIPT"
