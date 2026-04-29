#!/usr/bin/env bash

# Determine the directory where this script lives
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed or not in PATH."
    exit 1
fi

# Ensure 'schedule' is installed quietly
python3 -m pip install schedule >/dev/null 2>&1 || true

echo "Starting Weaver Daemon in the background..."
echo "Logs will be written to $DIR/../logs/weaver.log"

# Start the python script using nohup to detach it from the terminal
nohup python3 "$DIR/weaver.py" > /dev/null 2>&1 &

echo "Weaver is now running (PID $!)."
