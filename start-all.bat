@echo off
REM ======================================================================
REM  CLIP WATCHER - START ALL CHANNELS
REM  Watches every channel listed in channels.txt
REM ======================================================================

REM Edit the line below to change settings.
REM See SETUP GUIDE.txt Part 7 for all options.
set OPTIONS=--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2

REM For AI highlights, add --ai and optionally --ai-visual --ai-vision-key YOUR_KEY
REM set OPTIONS=--lengths 45 --ai --threshold 2 --min-msgs 5

python clipwatcher.py %OPTIONS%