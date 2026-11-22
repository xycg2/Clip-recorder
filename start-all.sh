#!/bin/bash
# ClipWatcher Startup Script (macOS / Linux)
# Make executable: chmod +x start-all.sh

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Default options - edit these to change behavior
OPTIONS="--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2"

# Uncomment and edit for AI features:
# OPTIONS="--lengths 45 --ai --ai-visual --ai-vision-key $OPENAI_API_KEY --threshold 2 --min-msgs 5"

# Run ClipWatcher with all channels from channels.txt
python clipwatcher.py $OPTIONS "$@"