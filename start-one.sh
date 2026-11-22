#!/bin/bash
# ClipWatcher Single Channel Startup Script (macOS / Linux)
# Make executable: chmod +x start-one.sh

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Default options - edit these to change behavior
OPTIONS="--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2"

# Prompt for channel
echo "Enter Twitch username or YouTube /live URL:"
read -r CHANNEL

if [ -z "$CHANNEL" ]; then
    echo "No channel entered. Exiting."
    exit 1
fi

# Run ClipWatcher with the specified channel
python clipwatcher.py "$CHANNEL" $OPTIONS "$@"