# ClipWatcher

### Automatically find and clip interesting moments from Twitch and YouTube livestreams.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/Platforms-Twitch%20%7C%20YouTube-blueviolet)](https://www.twitch.tv/)
[![AI](https://img.shields.io/badge/AI-Optional-blue)](#ai-highlight-detection)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

**ClipWatcher** automatically detects interesting moments in livestreams, eliminating the need to spend hours watching recordings to find highlights.

It monitors live chat activity, analyzes audio levels, and optionally uses AI to understand what's happening in the stream. When an interesting moment is detected, ClipWatcher automatically captures the footage and saves it as a video clip.

From sudden chat spikes and loud reactions to funny quotes and gameplay highlights, ClipWatcher helps you find the moments worth keeping.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [System Requirements](#system-requirements)
  - [Windows](#windows)
  - [macOS](#macos)
  - [Linux](#linux)
- [Python Environment (Virtual Environment)](#python-environment-virtual-environment)
- [Configuring Channels](#configuring-channels)
- [Running ClipWatcher](#running-clipwatcher)
- [AI Highlight Detection](#ai-highlight-detection)
  - [What You Need](#what-you-need)
  - [Get an OpenAI API Key](#1-get-an-openai-api-key-only-for---ai-visual)
  - [Install AI Dependencies](#2-install-ai-dependencies)
  - [Usage Examples](#3-usage-examples)
  - [AI Options Reference](#ai-options-reference)
  - [Choosing a Whisper Model](#choosing-a-whisper-model)
  - [How the AI Scoring Works](#how-the-ai-scoring-works)
  - [AI Outputs](#ai-outputs-enhanced)
  - [AI Tips & Tuning](#ai-tips--tuning)
  - [AI Troubleshooting](#ai-troubleshooting)
- [Configuration](#configuration)
  - [Available Options](#available-options)
  - [Recommended Presets by Streamer Size](#recommended-presets-by-streamer-size)
  - [Common Option Combinations](#common-option-combinations)
- [Output Structure](#output-structure)
- [Moment Ratings](#moment-ratings)
- [Captions](#captions)
- [Troubleshooting](#troubleshooting)
- [Frequently Asked Questions (FAQ)](#frequently-asked-questions-faq)
- [Requirements](#requirements)
- [License](#license)
## Features

| Feature | Description |
|:---|:---|
| **Twitch & YouTube** | Monitor livestreams across both platforms |
| **Chat Spike Detection** | Detect sudden increases in chat activity against a rolling 5-minute baseline |
| **Audio Analysis** | Detect loud moments and improve clip timing |
| **AI Highlight Detection** | Whisper transcription, GPT vision analysis, and chat sentiment analysis |
| **Multiple Channels** | Monitor several streamers simultaneously |
| **Auto-Recovery** | Automatically restart individual channel watchers after crashes |
| **Moment Ratings** | Classify clips as TOP, GOOD, or OK |
| **Organized Output** | Sort clips by channel and date, with CSV indexes and metadata |
| **Optional Captions** | Generate burned-in subtitles using whisper.cpp |

---

## Installation

ClipWatcher supports Windows, macOS, and Linux.

### System Requirements

| Resource | Minimum | Recommended |
|:---|:---|:---|
| **RAM** | 4 GB | 8 GB+ (16 GB for AI features) |
| **Disk Space** | 2 GB free | 50+ GB free (for overnight recordings) |
| **GPU** | Not required | NVIDIA GPU with 6+ GB VRAM (for AI speed) |
| **CPU** | Any x64 / ARM64 | Modern multi-core (AI transcription is CPU-intensive without GPU) |
| **Internet** | Stable broadband | Unlimited / high cap (stream recording uses 3–6 GB/hour) |

> **Note:** The core chat spike + audio detection uses only standard library and runs on any hardware. AI features (Whisper, sentiment, vision) require the optional dependencies and benefit significantly from a GPU.

### Windows

Open **PowerShell as Administrator** (recommended) and install the required dependencies:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id Streamlink.Streamlink
winget install -e --id yt-dlp.yt-dlp
winget install -e --id DenoLand.Deno
```

> **Why these tools?**
> - **Python 3.9+** — Runs ClipWatcher (3.12 recommended, but 3.9–3.13 all work)
> - **FFmpeg** — Records, cuts, and encodes video clips
> - **Streamlink** — Connects to Twitch streams
> - **yt-dlp** — Connects to YouTube streams (requires Deno for PO tokens)
> - **Deno** — Runtime yt-dlp uses to fetch YouTube's encrypted tokens

**If `winget` isn't found:** Install "App Installer" from the Microsoft Store, then reopen PowerShell.

**If `python` opens the Microsoft Store:** Go to Settings → Apps → Advanced app settings → App execution aliases → Turn OFF `python.exe` and `python3.exe`, then reopen PowerShell.

### macOS

Install [Homebrew](https://brew.sh/) if you haven't already.

Open Terminal and run:

```bash
brew install python@3.12
brew install ffmpeg
brew install streamlink
brew install yt-dlp
brew install deno
```

> **Note:** Homebrew installs Python as `python3`. Use `python3` in commands below, or add an alias: `alias python=python3`

### Linux

The following commands are for Ubuntu and Debian-based distributions.

Open a terminal and run:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg pipx curl unzip
```

Install Streamlink and yt-dlp via pipx (isolated environments, recommended):

```bash
pipx ensurepath
pipx install streamlink
pipx install yt-dlp
```

Install Deno:

```bash
curl -fsSL https://deno.land/install.sh | sh
```

**Restart your terminal** after installation (or run `source ~/.bashrc` / `source ~/.zshrc`).

For Fedora, Arch, and other distributions, install the equivalent packages using your distribution's package manager (e.g., `dnf`, `pacman`, `zypper`).

### Verify Installation

After installing the dependencies, **restart your terminal** and verify everything is available:

```bash
python --version        # or python3 --version on macOS/Linux
ffmpeg -version
streamlink --version
yt-dlp --version
deno --version
```

Each should print a version number. If any command is not found, restart your terminal and try again.

### Python Environment (Virtual Environment)

A **virtual environment** is an isolated Python folder that keeps ClipWatcher's dependencies separate from your system Python. This prevents conflicts with other projects.

Navigate to the ClipWatcher project directory:

```bash
cd /path/to/ClipWatcher
```

Create and activate a virtual environment:

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> If you get a script execution error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**Windows (Command Prompt / cmd.exe):**

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You'll see `(.venv)` in your prompt when active. **Activate this every time you use ClipWatcher.**

Install core Python dependencies (stdlib-only, so this is optional but recommended for consistency):

```bash
python -m pip install --upgrade pip
```

> **There is no `requirements.txt`** because the core program uses only Python standard library. The optional `requirements-ai.txt` is only for AI features (see [AI Highlight Detection](#ai-highlight-detection)).

---

## Configuring Channels

Edit `channels.txt` in the main ClipWatcher directory. **Create this file if it doesn't exist** (or copy from `channels.example.txt` if provided).

Add one streamer per line:

```text
# Twitch channels — use just the username (from twitch.tv/username)
xqc
kaicenat
shroud

# YouTube channels — use the channel's /live URL
https://www.youtube.com/@SomeStreamer/live
https://www.youtube.com/@AnotherCreator/live

# Lines beginning with # are ignored (use to temporarily disable)
# ninja
```

### URL Format Guide

| Platform | ✅ Correct Format | ❌ Wrong Format |
|:---|:---|:---|
| **Twitch** | `xqc` | `https://twitch.tv/xqc` |
| **YouTube** | `https://www.youtube.com/@Name/live` | `https://youtube.com/@Name` or video URLs |

**YouTube:** You **must** use the channel's `/live` URL, not a video URL or the channel homepage. The `/live` endpoint always points to the current live stream.

- ✅ `https://www.youtube.com/@Markiplier/live`
- ❌ `https://www.youtube.com/@Markiplier` (homepage)
- ❌ `https://www.youtube.com/watch?v=abc123` (specific video)

You can add as many channels as you want. Each channel runs in its own subprocess, so a crash in one doesn't affect the others.

ClipWatcher uses this file when launched without a specific channel argument.

**Tip:** You can change your monitored streamers at any time by editing `channels.txt`. Restart ClipWatcher to apply the changes.

---

## Running ClipWatcher

ClipWatcher can be launched directly from a terminal or through a Python IDE such as Visual Studio Code or PyCharm.

### Option 1: Run from an IDE

You don't need to use the terminal every time you want to start monitoring.

1. Open the ClipWatcher project folder in your preferred IDE.
2. Make sure your IDE is using the Python environment where ClipWatcher dependencies are installed (the `.venv` you created).
3. Open `channels.txt` and add the streamers you want to monitor.
4. Open `clipwatcher.py`.
5. Click **Run**.

ClipWatcher will load the configured channels from `channels.txt` when no specific channel is provided.

**Supported IDEs:**

- Visual Studio Code (select `.venv` as interpreter: `Ctrl+Shift+P` → "Python: Select Interpreter")
- PyCharm (configure project interpreter to point to `.venv/bin/python` or `.venv\Scripts\python.exe`)
- IDLE
- Other Python-compatible IDEs

### Option 2: Run from the Terminal

**First, activate your virtual environment** (see [Python Environment](#python-environment-virtual-environment) above).

To monitor all configured channels from `channels.txt`:

```bash
python clipwatcher.py
```

To monitor a specific channel (overrides `channels.txt`):

```bash
python clipwatcher.py xqc
```

For YouTube, quote the URL:

```bash
python clipwatcher.py "https://www.youtube.com/@SomeStreamer/live"
```

You can also customize detection settings:

```bash
# Lower threshold for testing on active chat
python clipwatcher.py xqc --threshold 1.5 --min-msgs 3

# Recommended starting presets:
# Small streamer (< 100 viewers): --threshold 1.5 --min-msgs 3
# Medium streamer (100–1000):    --threshold 2.0 --min-msgs 5 (default)
# Large streamer (1000+):        --threshold 3.0 --min-msgs 15
```

### Option 3: Use the Startup Scripts (Windows)

On Windows, you can simply double-click:

- **`start-all.bat`** — Watches all channels in `channels.txt` in one window
- **`start-one.bat`** — Prompts for a single channel name/URL and watches it

These scripts read the `OPTIONS` line inside them for default settings. Edit them in Notepad to change defaults.

**What the `.bat` files do:**
```bat
:: start-all.bat
set OPTIONS=--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2
python clipwatcher.py %OPTIONS%
```

```bat
:: start-one.bat
set /p CHANNEL=Enter channel name or URL:
set OPTIONS=--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2
python clipwatcher.py %CHANNEL% %OPTIONS%
```

### Option 4: Create Your Own Startup Script (macOS / Linux)

Create `start-all.sh`:

```bash
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
OPTIONS="--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2"
python clipwatcher.py $OPTIONS
```

Make it executable: `chmod +x start-all.sh`

### For Overnight Monitoring

- Keep the terminal window open. Minimizing it is fine.
- **Prevent sleep:**
  - **Windows:** Settings → Power → "When plugged in, put my device to sleep after" → **Never**
  - **macOS:** System Settings → Displays → Advanced → "Prevent automatic sleeping on power adapter" → **On**
  - **Linux:** Depends on DE; typically `systemd-inhibit` or power settings
- Ensure sufficient available disk space (~3–6 GB per hour of stream per channel).
- Clips will automatically accumulate in `clips/`, organized by channel and date.
- **Windows Update:** Pause updates overnight (Settings → Windows Update → Pause updates).

### Stopping ClipWatcher

Press `Ctrl+C` in the terminal window. It will:
1. Stop all recording subprocesses gracefully
2. Finalize any in-progress clips
3. Print a summary of clips saved per channel

---

## AI Highlight Detection

> [!NOTE]
> AI features are **optional**. Standard chat spike and audio detection work **without any API key** and run on any hardware.

AI analysis helps identify interesting moments that traditional chat and audio detection might miss.

It can detect:

- Funny or memorable quotes (via Whisper transcription)
- Visual highlights such as kills, wins, and reactions (via GPT-4V vision)
- Changes in chat sentiment (via transformer model)
- Interesting moments that don't necessarily produce a large chat spike

### What You Need

| Feature | Runs Where? | Requirements | API Key Needed? |
|:---|:---|:---|:---|
| **Audio Transcription (Whisper)** | Your GPU/CPU | `torch`, `openai-whisper` (~1–3 GB models) | **No** |
| **Chat Sentiment Analysis** | Your CPU | `transformers`, `accelerate` (~500 MB model) | **No** |
| **Visual Analysis (GPT-4V)** | OpenAI's servers | `openai` package + API credits | **Yes (OpenAI)** |

**Bottom line:** You only need an API key if you want `--ai-visual` (frame analysis). The audio and chat analyzers run 100% locally.

### 1. Get an OpenAI API Key (Only for `--ai-visual`)

1. Go to <https://platform.openai.com/api-keys>
2. Sign in or create an OpenAI account
3. Click **Create new secret key**
4. Name it (e.g., "ClipWatcher Vision")
5. **Copy the key immediately** — it starts with `sk-` and you won't see it again
6. Save it securely (password manager, `.env` file, etc.)

> **Cost:** Vision uses GPT-4o-mini by default (~$0.15 per 1M input tokens). At 1 frame every 5 seconds, that's ~17,000 frames/hour ≈ **$0.03–0.05/hour** per stream. Set billing limits in your OpenAI dashboard (Settings → Billing → Limits).

### 2. Install AI Dependencies

Activate your virtual environment first, then:

```bash
python -m pip install -r requirements-ai.txt
```

**First run downloads ~1–3 GB of models** (Whisper + sentiment transformer). They're cached in `~/.cache/` for later runs.

**Contents of `requirements-ai.txt`:**
```
torch>=2.0.0           # PyTorch (CPU or CUDA)
torchaudio>=2.0.0      # Audio processing for Whisper
numpy>=1.24.0          # Numerical computing
openai-whisper>=20231117  # Local speech-to-text
openai>=1.0.0          # OpenAI API client (vision only)
transformers>=4.35.0   # HuggingFace transformers (sentiment)
accelerate>=0.24.0     # Model loading optimization
sentencepiece>=0.1.99  # Tokenizer for sentiment model
```

> **GPU strongly recommended** for speed. CUDA (NVIDIA) or MPS (Apple Silicon) will be auto-detected. CPU works but Whisper transcription will be slower (2–5x realtime on modern CPUs).

### 3. Usage Examples

**Basic AI — Whisper audio + chat sentiment (NO API key needed):**

```bash
python clipwatcher.py xqc --ai --threshold 1.5 --min-msgs 3
```

**Full AI with vision (requires OpenAI API key):**

```bash
python clipwatcher.py xqc --ai --ai-visual --ai-vision-key sk-YOUR_KEY_HERE --ai-threshold 6.5
```

**Custom Whisper model and GPU acceleration:**

```bash
python clipwatcher.py xqc --ai --ai-whisper-model small --ai-device cuda
```

**Just vision, with a cheaper model:**

```bash
python clipwatcher.py xqc --ai --ai-visual --ai-vision-key sk-... --ai-vision-model gpt-4o-mini
```

**Add to startup script for overnight runs:**

Edit `start-all.bat` (or `start-all.sh`) and add to the `OPTIONS` line:
```bat
REM set OPTIONS=--lengths 45 --ai --ai-visual --ai-vision-key sk-YOUR_KEY --threshold 2 --min-msgs 5
```

### AI Options Reference

| Flag | Description | Default |
|:---|:---|:---|
| `--ai` | Enable all AI analyzers (audio + chat sentiment) | off |
| `--ai-audio / --no-ai-audio` | Toggle Whisper transcription | on with `--ai` |
| `--ai-whisper-model` | tiny / base / **small** / medium / large | `base` |
| `--ai-device` | auto / cpu / cuda / mps | `auto` |
| `--ai-visual` | Enable GPT-4V frame analysis (needs `--ai-vision-key`) | off |
| `--ai-vision-key` | **OpenAI API key** (starts with `sk-`) | *required for vision* |
| `--ai-vision-model` | gpt-4o-mini / gpt-4o / gpt-4-turbo | `gpt-4o-mini` |
| `--ai-vision-interval` | Analyze 1 frame every N seconds | `5` |
| `--ai-chat / --no-ai-chat` | Toggle chat sentiment analysis | on with `--ai` |
| `--ai-chat-model` | HuggingFace sentiment model | `cardiffnlp/twitter-roberta-base-sentiment` |
| `--ai-threshold` | Fusion score 0–10 to auto-clip | `6.5` |
| `--ai-check-interval` | Seconds between AI analysis passes | `30` |

### Choosing a Whisper Model

| Model | Speed (CPU) | Speed (GPU) | Accuracy | VRAM (GPU) | Best For |
|:---|:---|:---|:---|:---|:---|
| `tiny` | ~5x realtime | ~50x | Low | ~1 GB | Testing only |
| **`base`** | ~3x realtime | ~30x | Good | ~1 GB | **Default, balanced** |
| `small` | ~2x realtime | ~20x | Better | ~2 GB | Better accuracy |
| `medium` | ~1x realtime | ~10x | Best | ~5 GB | High accuracy needs |
| `large` | ~0.5x realtime | ~5x | Best | ~10 GB | Maximum accuracy |

> **Recommendation:** Start with `base` (default). If you have a GPU with 6+ GB VRAM, `small` is a great upgrade. `medium`/`large` only if accuracy is critical and you have the VRAM.

### How the AI Scoring Works

The AI analyzers feed into a **Fusion Scorer** that combines all signals into a 0–10 score:

| Signal | Weight | What It Detects |
|:---|:---|:---|
| **Audio AI (Whisper)** | 30% | Hype keywords, laughter, audio energy |
| **Visual AI (GPT-4V)** | 30% | Big plays, kills, reactions, visual gags |
| **Chat AI (Sentiment)** | 25% | Velocity spikes, positive sentiment, emotes, "clip it" keywords |
| **Audio Loudness (RMS)** | 10% | Existing sound spike detection |
| **Chat Spike (Statistical)** | 5% | Existing statistical spike detection |

When the **fusion score ≥ `--ai-threshold`** (default 6.5) and not on cooldown, a clip is created.

### AI Outputs (Enhanced)

When AI is enabled, ClipWatcher generates additional metadata:

- **Smart titles:** `[Epic Quote, Visual Highlight] StreamerName`
- **AI descriptions** with score breakdown bars in `credit.txt`
- **`_meta.json`** per clip — full AI analysis (transcript, vision response, sentiment, fusion breakdown)
- **Updated `clips.csv`** — "ai" trigger type + `ai_score` column
- **Audio AI** writes transcript snippets to chat.log with `[AI]` prefix

---

## Configuration

Edit `start-all.bat` / `start-all.sh` or `start-one.bat` to change the default settings.

```bat
REM Basic settings
set OPTIONS=--lengths 45 --threshold 2 --min-msgs 5 --cooldown 60 --after 15 --quality best --buffer-minutes 10 --status-minutes 2

REM Enable AI highlights (uncomment and add your key)
REM set OPTIONS=--lengths 45 --ai --ai-visual --ai-vision-key sk-YOUR_KEY --threshold 2 --min-msgs 5
```

### Available Options

| Option | Default | Description |
|:---|:---|:---|
| `--lengths` | `45` | Clip lengths in seconds. Supports multiple values, e.g. `30,45,60` |
| `--threshold` | `2.0` | Chat spike multiplier against the 5-minute average |
| `--min-msgs` | `5` | Minimum messages within 10 seconds to trigger a spike |
| `--cooldown` | `60` | Minimum seconds between clips |
| `--after` | `15` | Seconds of footage kept after the detected moment |
| `--quality` | `best` | Video quality: best, 1080p60, 720p60 |
| `--buffer-minutes` | `10` | Minutes of raw footage retained. Set to 0 to keep everything |
| `--audio-trigger` | `off` | Also trigger clips from loud moments without chat activity |
| `--skip-quiet` | `off` | Ignore chat spikes when the stream remains quiet |

### Recommended Presets by Streamer Size

| Streamer Size | `--threshold` | `--min-msgs` | Notes |
|:---|:---|:---|:---|
| **Small** (< 100 viewers) | 1.5 | 3 | Chat is quiet; lower threshold catches more |
| **Medium** (100–1,000) | 2.0 | 5 | Default; balanced |
| **Large** (1,000–10,000) | 3.0 | 15 | High baseline; needs bigger spikes |
| **Huge** (10,000+) | 4.0 | 30 | Very active chat; only major events |

### Common Option Combinations

```bash
# Small streamer, catch everything including loud moments
python clipwatcher.py smallstreamer --threshold 1.5 --min-msgs 3 --audio-trigger

# Big streamer, only the best moments
python clipwatcher.py bigstreamer --threshold 4.0 --min-msgs 30 --skip-quiet

# Overnight: multiple clip lengths, 10 min buffer, status every 2 min
python clipwatcher.py --lengths 30,45,60 --buffer-minutes 10 --status-minutes 2
```

---

## AI Tips & Tuning

- **Start without vision** (`--ai` only) to test — no API costs, runs fully local
- **Lower `--ai-threshold`** (e.g., 5.0) for more clips; raise (e.g., 8.0) for fewer
- **Adjust `--ai-check-interval`**: lower = more responsive but more CPU/GPU (default 30s)
- **Vision interval**: `--ai-vision-interval 10` = fewer API calls; `--ai-vision-interval 3` = more responsive
- **GPU makes Whisper much faster** — use `--ai-device cuda` (NVIDIA) or `--ai-device mps` (Apple Silicon)
- **Watch the first hour** and note which clips are good/bad, then tune threshold
- **Cost control**: Set a monthly budget in OpenAI dashboard (Settings → Billing → Limits)

---

## AI Troubleshooting

| Issue | Fix |
|:---|:---|
| `ImportError: torch` / `transformers` | Run `pip install -r requirements-ai.txt` again |
| `CUDA out of memory` | Use `--ai-whisper-model base` or `--ai-device cpu` |
| `openai.AuthenticationError` | Check your API key is correct and has credits |
| `Rate limit exceeded` | Increase `--ai-vision-interval` or lower `--ai-check-interval` |
| Whisper very slow on CPU | Use `--ai-whisper-model tiny` or get a GPU |
| No AI clips at all | Lower `--ai-threshold` to 5.0, check logs for `AI Score:` lines |
| Too many AI clips / low quality | Raise `--ai-threshold` to 7.5–8.0 |

---

## Output Structure

Clips are automatically organized by channel and recording date.

```text
clips/
├── xqc/
│   ├── 2026-11-16/
│   │   ├── 031542_45s.mp4
│   │   ├── 031542_credit.txt
│   │   ├── 031542_meta.json
│   │   └── 031542_45s_captioned.mp4
│   ├── clips.csv
│   ├── chat.log
│   └── _buffer/
│
└── youtube-SomeStreamer/
    └── ...
```

| File | Description |
|:---|:---|
| `.mp4` | Recorded video clip |
| `_credit.txt` | Streamer link and chat context |
| `_meta.json` | AI analysis and metadata |
| `_captioned.mp4` | Video with burned-in subtitles |
| `clips.csv` | Index of all generated clips |
| `chat.log` | Recorded chat history |
| `_buffer/` | Temporary recording storage |

**Credit:** Every clip includes a `credit.txt` file containing the streamer's link. Always credit and link the original streamer when publishing clips.

---

## Moment Ratings

Every detected clip receives a rating based on chat and audio activity.

| Rating | Meaning |
|:---|:---|
| **TOP** | Chat activity and audio both spike, or one signal is exceptionally strong |
| **GOOD** | Strong chat and audio reaction, or a significant chat spike during a quiet moment |
| **OK** | Smaller reaction that may still be worth reviewing |

To find the best clips, sort `clips.csv` by:

1. `rating` — TOP first.
2. `chat_ratio` — Highest first.

---

## Captions

ClipWatcher can optionally generate burned-in subtitles using `whisper.cpp`.

### Setup (Windows)

1. Download `whisper-cli.exe` from [whisper.cpp releases](https://github.com/ggml-org/whisper.cpp/releases) → `whisper-bin-x64.zip`
2. Extract into `whisper/` folder in your ClipWatcher directory
3. Download `ggml-small.en.bin` from [HuggingFace](https://huggingface.co/ggerganov/whisper.cpp/tree/main) (≈470 MB)
4. Place the model inside `models/`

Your directory should look like:

```text
ClipWatcher/
├── whisper/
│   └── whisper-cli.exe
└── models/
    └── ggml-small.en.bin
```

Add to `start-all.bat`:

```bat
set OPTIONS=--lengths 45 --captions --whisper-bin whisper\whisper-cli.exe --whisper-model models\ggml-small.en.bin
```

### Setup (macOS)

```bash
# Install whisper.cpp via Homebrew
brew install whisper-cpp

# Download model
mkdir -p models
curl -L -o models/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
```

Add to `start-all.sh`:

```bash
OPTIONS="--lengths 45 --captions --whisper-bin whisper-cli --whisper-model models/ggml-small.en.bin"
```

### Setup (Linux)

```bash
# Build whisper.cpp from source (or use a prebuilt binary)
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
make
# Copy whisper-cli to your ClipWatcher folder
cp whisper-cli /path/to/ClipWatcher/whisper/

# Download model
mkdir -p /path/to/ClipWatcher/models
curl -L -o /path/to/ClipWatcher/models/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin
```

Add to `start-all.sh`:

```bash
OPTIONS="--lengths 45 --captions --whisper-bin whisper/whisper-cli --whisper-model models/ggml-small.en.bin"
```

### Notes

- Use `small.en` rather than `medium.en`: medium is much slower on CPU and can fall behind on busy nights.
- Captions run in the background, so plain clips are always saved first.
- Captioned files are named `*_captioned.mp4` alongside the original.
- The `--whisper-bin` path is relative to the ClipWatcher directory.

---

## Troubleshooting

| Problem | Solution |
|:---|:---|
| `Missing on PATH: ffmpeg` (or streamlink, yt-dlp, deno) | Restart your terminal after install. Verify with `ffmpeg -version` etc. |
| Stuck on "Waiting for ... to go live" | Streamer is offline, or name/link is wrong. Check in browser. Update yt-dlp: `pipx upgrade yt-dlp` or `winget upgrade yt-dlp.yt-dlp` |
| "Couldn't understand YouTube link" | Use channel's `/live` URL: `https://www.youtube.com/@Name/live` (not video URL or homepage) |
| Too many irrelevant clips | Increase `--threshold` or `--min-msgs`, or enable `--skip-quiet` |
| No clips after hours | Lower `--threshold` to 1.5–2.5, check for `SPIKE` lines in output |
| Clips start too early or late | Adjust `--after` (default 15s). If "sound: LOUD" clips feel off, try `--audio-boost 12` |
| Disk filling up | Avoid `--buffer-minutes 0` (keeps full raw stream ~3–6 GB/hr). Default 10 min is safe. |
| `python` opens Microsoft Store (Windows) | Settings → Apps → Advanced app settings → App execution aliases → Turn OFF `python.exe`/`python3.exe` |
| `winget` not found (Windows) | Install "App Installer" from Microsoft Store |
| YouTube: "The page needs to be reloaded" | Update yt-dlp and ensure Deno is installed. Try: `yt-dlp -F "https://www.youtube.com/@Name/live"` |
| Sound: "no audio found in stream" | Rare. Sound features disable for that stream; clips use chat timing only. |
| Clips have no audio / audio out of sync | Re-encoding is used (not stream copy). If persists, check FFmpeg version. |

---

## Frequently Asked Questions (FAQ)

### General

**Q: Can ClipWatcher clip VODs or past broadcasts?**
A: No. It only works on **live** streams. It cannot download or clip from VODs.

**Q: Do I need a Twitch or YouTube account?**
A: No. ClipWatcher reads chat anonymously (Twitch IRC, YouTube live chat) and never posts anything. No login required.

**Q: Does it work on Linux / macOS?**
A: Yes. Core functionality works on all platforms. The `.bat` files are Windows-only; use `.sh` scripts or run `python clipwatcher.py` directly. Captions require platform-specific `whisper.cpp` builds.

**Q: How much disk space do I need?**
A: ~3–6 GB per hour of stream per channel (1080p60). Clips are ~50–100 MB per 45s. With default `--buffer-minutes 10`, only recent raw footage is kept.

**Q: Can I run multiple instances?**
A: Yes, but each needs its own folder (or use `--out` to separate output). Running multiple watchers on the same stream is redundant.

### Configuration

**Q: What's a good `--threshold` for my streamer?**
A: See [Recommended Presets by Streamer Size](#recommended-presets-by-streamer-size). Start with defaults, watch for `SPIKE` lines, then adjust.

**Q: What does `--cooldown 60` mean?**
A: Minimum 60 seconds between clips. Prevents spam from sustained chat activity.

**Q: What does `--after 15` do?**
A: Keeps 15 seconds of footage **after** the detected moment. The clip starts at `moment_time - (length - after)`.

**Q: What is `--buffer-minutes`?**
A: How many minutes of raw stream footage to keep in `_buffer/`. Default 10 minutes. Set to 0 to keep everything (⚠️ huge disk usage).

### AI Features

**Q: Do I need an API key for AI?**
A: Only for `--ai-visual` (GPT-4V vision). Audio (Whisper) and chat sentiment run locally with no key.

**Q: How much does vision cost?**
A: ~$0.03–0.05/hour per stream with GPT-4o-mini (1 frame/5s). Set billing limits in OpenAI dashboard.

**Q: Can I use a local vision model instead of OpenAI?**
A: Not yet. The code supports `llava-python` and `moondream` in `requirements-ai.txt` (commented out) but they're not integrated.

**Q: Whisper is slow on my CPU. What can I do?**
A: Use `--ai-whisper-model tiny` or `--ai-device cpu` (explicit), or get an NVIDIA GPU for CUDA acceleration.

### Output

**Q: Where are my clips?**
A: In `clips/<channel>/<date>/` — e.g., `clips/xqc/2026-11-16/031542_45s.mp4`

**Q: What's in `credit.txt`?**
A: Streamer's channel link, clip timestamp, chat context, and rating. **Always credit the streamer when posting.**

**Q: Can I open `clips.csv` in Excel?**
A: Yes. It has columns: time, rating, trigger, chat_ratio, msgs, sound_db, top_chat, files, ai_score.

**Q: What's `_meta.json`?**
A: Full AI analysis for the clip (transcript, vision response, sentiment scores, fusion breakdown). Only created with `--ai`.

---

## Requirements

### Core (Required)

| Component | Version | Purpose |
|:---|:---|:---|
| **Python** | 3.9+ | Runtime |
| **FFmpeg** | Any recent | Recording, audio analysis, video encoding |
| **Streamlink** | 6.0+ | Twitch stream access |
| **yt-dlp** | 2024.01+ | YouTube stream access |
| **Deno** | 1.40+ | YouTube PO token support (required by yt-dlp) |

### AI Features (Optional)

| Component | Version | Purpose |
|:---|:---|:---|
| **PyTorch** | 2.0+ | Whisper & sentiment models |
| **torchaudio** | 2.0+ | Audio preprocessing |
| **openai-whisper** | 20231117+ | Local speech-to-text |
| **openai** | 1.0+ | GPT-4V vision API |
| **transformers** | 4.35+ | Chat sentiment model |
| **accelerate** | 0.24+ | Model loading optimization |
| **sentencepiece** | 0.1.99+ | Tokenizer |

### Captions (Optional)

| Component | Purpose |
|:---|:---|
| **whisper.cpp** | `whisper-cli` binary for fast subtitle generation |
| **ggml-small.en.bin** | English Whisper model (~470 MB) |

---

## License

This project is licensed under the [MIT License](LICENSE) — see the LICENSE file for details.

> **Note:** The MIT License badge at the top of this README links to the `LICENSE` file in the repository root. Make sure to include a `LICENSE` file when publishing.