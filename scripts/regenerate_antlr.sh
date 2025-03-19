#!/bin/bash
# Bash script to regenerate ANTLR4 files for GeLB
# This script should be run from the root of the GeLB repository

set -e

echo "Regenerating ANTLR4 files..."

# Ensure we're in the virtual environment
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run gelb_bootstrap.sh first." >&2
    exit 1
fi

# Activate virtual environment and run Python command
./venv/bin/python -c "from gelb.utils.misc import invoke_antlr4_tool; invoke_antlr4_tool()"

if [ $? -eq 0 ]; then
    echo "ANTLR4 files regenerated successfully."
else
    echo "Failed to regenerate ANTLR4 files." >&2
    exit 1
fi
