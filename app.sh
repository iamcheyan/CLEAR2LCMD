#!/bin/bash

# This script wraps the python backup utility
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/cleanup_backup.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: cleanup_backup.py not found in $SCRIPT_DIR"
    exit 1
fi

echo "--- Mac Storage Cleanup & Backup Utility ---"
python3 "$PYTHON_SCRIPT"
