#!/bin/bash
# AutoClipper Cron Launcher
# Add to crontab: 0 * * * * /path/to/auto-clipper/scripts/run.sh
#
# Supports all auto_clipper.py arguments, e.g.:
#   ./run.sh run --force
#   ./run.sh run --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SKILL_DIR/logs"
LOCK_FILE="$LOG_DIR/auto-clipper.lock"

mkdir -p "$LOG_DIR"

# Verify ffmpeg is installed
if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg not found on PATH. Install it first." >&2
    exit 1
fi

# Check for existing process
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Already running (PID: $PID), exiting"
        exit 0
    fi
    rm -f "$LOCK_FILE"
fi

# Write our PID
echo $$ > "$LOCK_FILE"

cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Run the clipper
cd "$SKILL_DIR"
python3 "$SCRIPT_DIR/auto_clipper.py" "${@:-run}"
