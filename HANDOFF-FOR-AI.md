# Handoff: Clip Watcher project

Give this file to any AI coding agent (Claude Code, Cursor, ChatGPT, etc.) with this folder open.
It explains what was built, what was decided, what's tested, and what's left.

## Goal (from the user)

Auto-clip **live Twitch and YouTube streams** where chat spikes, unattended for many hours (overnight),
so the user can **post the clips the next day**.

- Clip length: **45s** by default. The `--lengths` option can select other durations if needed.
- **Clips must never be deleted.** Only raw scratch footage is cleaned up.
- Runs on the user's **desktop PC** (assumed **Windows**, not yet confirmed), not the MacBook where it was written.
- The user is **not very technical**. Prefer double-click files and plain step-by-step instructions.
- Rule: when posting, **credit and link the streamer**. Each clip gets a credit file for this.

Based on a "Clip Watcher" recipe: streamlink to record, anonymous Twitch IRC to read chat,
spike detection (msgs per 10s vs. 3x the 5-minute average), ffmpeg to cut, whisper.cpp for captions.

## Files

| File | Purpose |
|---|---|
| `clipwatcher.py` | The whole program. Python 3.9+, standard library only. |
| `channels.txt` | One channel per line (Twitch name or YouTube channel link), `#` = ignored. Read by `start-all.bat`, which passes each line quoted (YouTube links can contain `&`). |
| `start-all.bat` | Runs `python clipwatcher.py %OPTIONS%` (no channel), so everyone in channels.txt is watched in one window. `set OPTIONS=` holds the shared flags. |
| `start-one.bat` | Prompts for one channel and runs it. |
| `SETUP GUIDE.txt` | Detailed, non-technical Windows guide (install, choosing channels, testing, overnight run, settings, captions, troubleshooting). Keep it in sync with any code or flag changes. |
| `HANDOFF-FOR-AI.md` | This file. |

The `.bat` files and the guide use **CRLF** line endings on purpose (Windows). Keep them that way.

## How clipwatcher.py works

Usage: `python clipwatcher.py [SOURCE] [options]`, where SOURCE is a Twitch name or a YouTube link.

- **With SOURCE**: `run_one()` watches that single channel.
- **Without SOURCE** (also double-click, or an editor's Run button): `run_all()` reads `channels.txt` (`--channels-file`,
  resolved next to the script), validates each line with `parse_source()` (bad lines are skipped with a message), checks
  the tools needed for the sites used, prints a banner, and launches one child process per channel:
  `sys.executable -u clipwatcher.py <entry> <same options>`, with `PYTHONIOENCODING=utf-8`. Child output is relayed
  prefixed with a coloured channel label. A child that dies within 20s is reported and not restarted (config error);
  otherwise it restarts after 30s. Ctrl+C reaches the children through the shared console; the parent waits up to 15s
  each, then prints the moments clipped per channel (counted from relayed "CLIP SAVED" lines). `pause_on_windows()`
  keeps a double-clicked window open at the end and on errors.
- `--out` defaults to `clips/` next to the script, not the current folder.
- Feedback: run_one prints a `STATUS |` line after 1 minute, then every `--status-minutes` (default 5): live duration,
  chat msgs/min, moments/files clipped, last clip time. Spikes print "SPIKE!" plus "cutting clips...", and successes print
  "CLIP SAVED hh:mm:ss: 30s, 45s, 60s (N MB) -> folder".

`parse_source()` decides the site. A YouTube `@handle`, `/channel/`, `/c/` or `/user/` link is normalised to `.../live`.
A watch, youtu.be or `/live/ID` link becomes `watch?v=ID`. The output folder is `clips/<name>` for Twitch and
`clips/youtube-<name>` for YouTube.

Threads:
1. **Recorder**: Twitch uses `streamlink https://twitch.tv/CH <quality> --stdout --retry-streams 30 --retry-max 0`.
   YouTube uses `yt-dlp -f <fmt> -o - --no-part --match-filters is_live URL`, which exits when the channel isn't live;
   the loop retries every 30s. `ytdlp_format()` maps `best` to `b` and `720p60` to `b[height<=720]/b`.
   (streamlink 7.6's YouTube plugin failed on every live channel in testing, saying "does not support VOD content",
   which is why YouTube uses yt-dlp.) Either one is piped into
   `ffmpeg -f segment -segment_time 10 -strftime 1` (no `-reset_timestamps`, so timestamps stay continuous) writing
   `clips/CH/_buffer/seg_YYYYmmdd-HHMMSS.ts`. Segment names = **wall-clock arrival time**. This keeps chat and video
   aligned even when Twitch ad-filtering or drops leave gaps, which a single growing file with a fixed offset would not.
   Old segments (> `--buffer-minutes`, default 10) are pruned. `0` keeps everything. When streamlink exits
   (stream ended), it loops back to waiting.
2. **Chat**:
   - **TwitchChat**: raw socket to `irc.chat.twitch.tv:6667`, nick `justinfanNNNNN`, no token, answers PING,
     reconnects on error.
   - **YouTubeChat**: runs `yt-dlp --skip-download --write-subs --sub-langs live_chat --no-part --match-filters is_live`
     into `_chat_tmp/` and tails the growing `chat.live_chat.json` (JSON lines). `youtube_messages()` searches each
     line recursively for `liveChatTextMessageRenderer` / `liveChatPaidMessageRenderer`, so it doesn't depend on the
     exact wrapper. Emoji runs become their `:shortcut:`. Restarts every 30s when yt-dlp exits.
     The `chat-downloader` package was tried and rejected: it hung and is unmaintained.
   - Both log to `clips/<name>/chat.log` (ISO time, user, message, tab-separated).
3. **Detector** (main loop, ticks every second): 10s buckets. Spike if count >= `threshold` x mean of the last 30 buckets
   **and** count >= `min-msgs`, after 2 min warm-up, with `cooldown` between spikes. Records the top 3 repeated messages.
   Spikes are skipped if the recorder isn't live (newest segment older than 30s).
4. **AudioMeter** (sound; off with `--no-audio`): for every closed segment, `measure_loudness()` decodes the audio with
   ffmpeg to mono 8 kHz s16le on stdout and computes RMS dB per 0.5s window (pure Python, `array('h')`). It keeps the
   last 20 min of `(time, dB)`. `baseline(at)` is the median of the 5 min before `at` (needs 2 min of data), so loud
   games or streamers raise "normal". `peak(start, end)` and `wait_covered()` are used by handle_moment. If 3 segments
   have no audio, it logs once and sound features stay off. With `--audio-trigger`, `_check_trigger()` fires `on_loud()`
   when 2 readings within about 1.5s are `--audio-trigger-db` (14) above baseline, with a 30s internal cooldown.
5. **handle_moment** (one thread per moment; replaces the old handle_spike): a clip ends at `t + --after` and starts at
   `end - L`. For chat spikes it waits for the footage, then looks for the loudest sound in
   `[t - --audio-lookback, t + 5]`. If that's at least `--audio-boost` (8 dB) above baseline, the clip is re-anchored:
   `t = peak time`, so it ends `--after` seconds after the actual moment instead of after the chat reaction.
   `--skip-quiet` drops chat spikes whose sound stayed under boost/2. `rate_moment()` gives TOP / GOOD / OK: chat is
   1 point, +1 if ratio >= 2x threshold; LOUD is 1 point, +1 if >= 1.5x boost; 3+ points = TOP, 2 = GOOD, otherwise OK.
   A shared `claim()` in run_one (moments within `--cooldown` of each other) stops chat and sound from clipping the same
   moment twice; chat moments are claimed at `bucket start - 5s`.
   `cut_clip` joins the covering segments with the `concat:` protocol (run with `cwd=seg_dir`, bare names), trims with
   `-ss` AFTER `-i` (exact), and re-encodes (libx264 veryfast crf 20, aac 160k, `aresample=async=1`, `+faststart`) to `clips/CH/YYYY-MM-DD/HHMMSS_{L}s.mp4`. It also writes `HHMMSS_credit.txt` (includes the rating) and
   appends to `clips/CH/clips.csv` with these columns: time, rating, trigger, chat_ratio, msgs_in_10s,
   avg_msgs_per_10s, sound, sound_db_above_normal, top_chat, files. A csv with an older header is renamed to
   clips_old.csv.
6. **Captions** (optional, `--captions --whisper-bin ... --whisper-model ...`): a queue worker extracts 16 kHz wav, runs
   `whisper-cli -osrt`, then burns subtitles with libx264 into `*_captioned.mp4`. It runs with `cwd` set to the clip
   folder and bare filenames to avoid Windows path escaping in `-vf subtitles=`.

Flags (the user set these defaults: 45s clips, threshold 2, min-msgs 5, status every 2 min):
`--lengths 45  --after 15  --quality best  --threshold 2  --min-msgs 5  --cooldown 60  --buffer-minutes 10
--status-minutes 2  --out clips  --no-audio  --audio-boost 8  --audio-lookback 20  --skip-quiet  --audio-trigger
--audio-trigger-db 14  --captions  --whisper-bin whisper-cli  --whisper-model PATH`

The user has added their own comments in the code. Keep them.

## What's tested and what isn't

Tested on the Mac (no ffmpeg or streamlink installed there):
- `py_compile` passes.
- Sound, using a stand-in ffmpeg that outputs synthetic sine PCM:
  - A sine at amplitude 0.5 measures -9.0 dB.
  - With 400s of normal audio, a scream, and a chat spike 7s later, the clip is re-anchored to end exactly 15s after
    the scream (chat-only timing would have ended it 22s after) and is rated TOP.
  - A chat spike while quiet is rated GOOD; with `--skip-quiet` it is skipped.
  - The sound-only trigger fires once, at the right second.
  - A sound-only clip writes its csv and credit file correctly, and an old csv is renamed to clips_old.csv.
- **Not tested:** sound on real stream audio, and the default thresholds (8 dB boost, 14 dB trigger) on real
  streams. Expect to tune them.
- Detector unit test: steady chat for 5 min then a burst gives exactly one spike at the right time and the correct top message.
- `cut_clip` segment selection and `-ss`/`-t` math with fake segment files and a stubbed ffmpeg: correct for 30, 45 and 60.
- Live anonymous IRC: connected to real channels and parsed real messages into chat.log.
- Multi-channel mode end to end (3.5 min, 2 real Twitch chats, stand-in ffmpeg and streamlink scripts, low threshold):
  banner, prefixed output, LIVE, STATUS lines, SPIKE, CLIP SAVED with 30/45/60 files plus credit.txt and clips.csv,
  and a clean Ctrl+C with a summary. Also tested: empty channels file, an invalid line, and missing tools.
- `parse_source()` on Twitch names and URLs, and YouTube @handle, /channel/, watch?v=, youtu.be and /live/ID links.
- YouTubeChat against a **fake** yt-dlp that writes live_chat.json lines incrementally (including emoji and a broken
  line): messages parsed and logged correctly.
- Real yt-dlp (old 2025.10 build, the newest available for the Mac's Python 3.9) **found** the live video ID for a
  24/7 channel, then failed with "The page needs to be reloaded". A current yt-dlp with Deno on the PC should be fine,
  but that's unconfirmed.

- Audio sync (2026-11-18, real Twitch footage): the old stream-copy cut left the audio ~2s off the video in players
  that ignore MP4 edit lists. Re-encoding fixed it: both tracks start at 0, are 45.000s long, and the audio matches the
  source with 0 ms offset. A 45s 1080p60 clip encodes in about 26s on the MacBook. Don't go back to `-c copy`.

**NOT tested yet:**
- **Any real YouTube recording or chat with current yt-dlp + Deno.** Check that `-o -` streams mpegts the segmenter
  accepts, and that live_chat is written incrementally while live. If `--match-filters is_live` misbehaves on
  `/@handle/live` URLs, drop it.
- Real streamlink + ffmpeg segment recording (`-strftime` naming, `-map 0:v? -map 0:a?`).
- Real concat cut. Check the clips play, have audio, and start close to the intended time.
- The caption pipeline (whisper.cpp release zip layout, libass in the Gyan FFmpeg build).
- The `.bat` files on real Windows.
- Long multi-hour stability and reconnects.

## Next steps

1. **Confirm the desktop's OS** with the user. If it's Linux or macOS, add `start-all.sh` and adjust the guide.
2. Help the user through `SETUP GUIDE.txt` Parts 2 to 4 on the PC: winget installs of Python, FFmpeg, Streamlink,
   yt-dlp and Deno, then a test run with `--threshold 1.5 --min-msgs 3` on a currently-live Twitch channel **and** a
   live YouTube channel. Fix whatever errors they paste.
3. After a successful test, tune the defaults (threshold, min-msgs per chat size, `--after`) from their feedback.
4. Possible improvements, only if the user wants them:
   - Rank or merge clips (e.g. skip the 30s version when the spike is long).
   - A simple daily summary of the best clips (sort by ratio).
   - A Windows Task Scheduler entry to auto-start at boot.
   - Phone alerts when a clip is saved (e.g. a Discord webhook with the clip attached), so the user can post first.
     This was offered and not yet answered.
   - AI rating and titles per clip. This was discussed and not yet requested.

Note: the user once declined a PowerShell auto-install script (`setup-windows.ps1`) and asked for an explanation instead.
Ask before adding scripts that install software.

## AI Highlight Detection (Added 2026-11-21)

New AI-powered highlight detection system added to complement the existing chat spike + sound detection.

### New Components

| Class | Purpose |
|-------|---------|
| `WhisperAudioAnalyzer` | Audio transcription + hype keyword detection + laughter + energy analysis |
| `VisionAnalyzer` | Visual frame analysis using OpenAI GPT-4V (or compatible) |
| `ChatSentimentAnalyzer` | Chat velocity, sentiment (transformer), emote density, keywords |
| `FusionScorer` | Weighted fusion of all AI signals + existing audio loudness + chat spike ratio |

### New CLI Flags

- `--ai` - Enable all AI analyzers (audio + chat sentiment by default)
- `--ai-audio / --no-ai-audio` - Toggle Whisper audio analysis
- `--ai-whisper-model` - Whisper model: tiny/base/small/medium/large (default: base)
- `--ai-device` - Device: auto/cpu/cuda/mps (default: auto)
- `--ai-visual` - Enable vision analysis (requires `--ai-vision-key`)
- `--ai-vision-key` - OpenAI API key for GPT-4V
- `--ai-vision-model` - Vision model (default: gpt-4o-mini)
- `--ai-vision-interval` - Frame analysis interval in seconds (default: 5)
- `--ai-chat / --no-ai-chat` - Toggle chat sentiment analysis
- `--ai-chat-model` - HuggingFace sentiment model (default: cardiffnlp/twitter-roberta-base-sentiment)
- `--ai-threshold` - Fusion score threshold 0-10 to auto-clip (default: 6.5)
- `--ai-check-interval` - Seconds between AI analysis passes (default: 30)

### Architecture

1. **AI Analysis Loop** (background thread, runs every `--ai-check-interval`):
   - Scans new 10s segments in the buffer
   - Runs all enabled AI analyzers in parallel
   - Feeds results to `FusionScorer`
   - If score >= threshold and not on cooldown, creates clip via `handle_moment`

2. **Integration with Existing Pipeline**:
   - `handle_moment` now accepts `ai_analyzers` and `fusion_scorer` params
   - AI clips get `source="ai"` and include `ai_score`, `ai_breakdown`, `ai_results`
   - Enhanced credit.txt with AI title, description, score breakdown
   - New `_meta.json` file per AI clip with full analysis
   - clips.csv updated with "ai" trigger type and score column

3. **Fusion Scorer Weights**:
   ```python
   weights = {
       "audio_ai": 0.30,      # Whisper transcription + hype + laughter
       "visual_ai": 0.30,     # Vision model frame analysis
       "chat_ai": 0.25,       # Chat velocity + sentiment + emotes
       "audio_loudness": 0.10, # Existing RMS loudness
       "chat_spike": 0.05,    # Existing statistical spike
   }
   ```

### Dependencies (requirements-ai.txt)

```
torch>=2.0.0
torchaudio>=2.0.0
numpy>=1.24.0
openai-whisper>=20231117
openai>=1.0.0
transformers>=4.35.0
accelerate>=0.24.0
sentencepiece>=0.1.99
```

### Testing Notes

- **Not yet tested on real streams**: AI thresholds (6.5 default) and weights need tuning
- **Whisper model choice**: base recommended for CPU; small/medium for GPU
- **Vision API costs**: gpt-4o-mini is ~$0.15/1M input tokens; 1 frame/5s = ~17k frames/hour
- **Chat sentiment**: roberta-base runs on CPU, adds ~50-100ms per batch
- **Learning loop**: `FusionScorer.record_feedback()` exists but no UI yet; user would need to manually call it

### Next Steps for AI

1. Tune `--ai-threshold` and weights based on real stream testing
2. Add simple feedback mechanism (approve/reject clips to retrain weights)
3. Consider local vision models (LLaVA, Moondream) to avoid API costs
4. Add Discord/webhook notifications with AI-generated titles
5. Daily summary of top AI clips sorted by score
