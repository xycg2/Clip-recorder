@echo off
REM ======================================================================
REM  CLIP WATCHER - START ONE CHANNEL
REM  Prompts for a single Twitch or YouTube channel to watch
REM ======================================================================

REM Edit the line below to change settings.
REM See SETUP GUIDE.txt Part 7 for all options.
set OPTIONS=--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2

REM For AI highlights, add --ai and optionally --ai-visual --ai-vision-key YOUR_KEY
REM set OPTIONS=--lengths 45 --ai --threshold 2 --min-msgs 5

echo.
echo ======================================================================
echo  CLIP WATCHER - Single Channel
echo ======================================================================
echo.
echo Enter a Twitch name (e.g. xqc) or a YouTube channel link:
echo Example: https://www.youtube.com/@SomeStreamer/live
echo.

set /p CHANNEL="Channel: "

if "%CHANNEL%"=="" (
    echo No channel entered. Exiting.
    timeout /t 3
    exit /b
)

echo.
echo Starting clip watcher for: %CHANNEL%
echo Options: %OPTIONS%
echo.

python clipwatcher.py %CHANNEL% %OPTIONS%

echo.
echo Done. Press any key to close...
pause >nul