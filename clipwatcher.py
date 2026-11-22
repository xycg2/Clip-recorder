
import argparse
import collections
import csv
import datetime as dt
import json
import math
import os
import queue
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from array import array
from bisect import bisect_left, insort
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

SCRIPT_DIR = Path(__file__).resolve().parent
SEG_SECONDS = 10                                                                                    # length of each buffer segment
SEG_RE = re.compile(r"seg_(\d{8}-\d{6})\.ts$")
STOP = threading.Event()

# =============================================================================
# AI ANALYZERS - Intelligent highlight detection
# =============================================================================

@dataclass
class AIResult:
    """Result from an AI analyzer."""
    analyzer: str
    score: float  # 0-10
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class AIAnalyzerBase:
    """Base class for AI analyzers."""
    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.model = None

    def warmup(self):
        """Load models. Override in subclasses."""
        pass

    def analyze(self, segment_path: Path, context: dict) -> AIResult:
        """Analyze a segment. Override in subclasses."""
        if not self.enabled:
            return AIResult(analyzer=self.name, score=0.0, details={"disabled": True})
        return AIResult(analyzer=self.name, score=0.0, details={"not_implemented": True})


class WhisperAudioAnalyzer(AIAnalyzerBase):
    """Audio analysis using Whisper: transcription + hype keywords + laughter + energy."""

    HYPE_KEYWORDS = [
        "pog", "poggers", "pogchamp", "let's go", "lets go", "insane", "crazy",
        "unbelievable", "no way", "omg", "wtf", "holy", "clutch", "godlike",
        "cracked", "nutty", "disgusting", "filthy", "sick", "nasty", "monster",
        "beast", "goat", "carry", "throwing", "choke", "ez", "free", "gifted"
    ]

    def __init__(self, model_name: str = "base", device: str = "auto", enabled: bool = True):
        super().__init__("audio_ai", enabled)
        self.model_name = model_name
        self.device = device
        self._whisper = None

    def warmup(self):
        if not self.enabled:
            return
        try:
            import whisper
            import torch
            if self.device == "auto":
                if torch.cuda.is_available():
                    self.device = "cuda"
                elif torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"
            log(f"  Loading Whisper {self.model_name} on {self.device}...")
            self._whisper = whisper.load_model(self.model_name, device=self.device)
            log(f"  Whisper ready")
        except ImportError:
            log("  Whisper not installed, audio AI disabled")
            self.enabled = False
        except Exception as e:
            log(f"  Whisper load failed: {e}")
            self.enabled = False

    def analyze(self, segment_path: Path, context: dict) -> AIResult:
        if not self.enabled or not self._whisper:
            return AIResult(analyzer="audio_ai", score=0.0, details={"error": "not_loaded"})

        start = time.time()
        details = {}

        try:
            import whisper
            import numpy as np

            # Load audio
            audio = whisper.load_audio(str(segment_path))
            audio = whisper.pad_or_trim(audio)

            # Energy analysis
            energy = float(np.sqrt(np.mean(audio**2)))
            details["energy"] = energy

            # Transcribe
            result = self._whisper.transcribe(audio, fp16=self.device != "cpu")
            text = result.get("text", "").strip().lower()
            details["transcript"] = text[:200]  # truncate for logging
            details["language"] = result.get("language", "unknown")

            # Keyword detection
            matches = [kw for kw in self.HYPE_KEYWORDS if kw in text]
            details["hype_keywords"] = matches
            keyword_score = min(len(matches) * 1.5, 10.0)

            # Laughter detection
            laughter_patterns = [
                r"\b(ha\s*){3,}\b", r"\b(lol|lmao|rofl|lul)\b", r"\b(xd+)\b",
                r"[😂🤣😆😭]"
            ]
            laughter_count = sum(len(re.findall(p, text)) for p in laughter_patterns)
            details["laughter_count"] = laughter_count
            laughter_score = min(laughter_count * 2.0, 10.0)

            # Energy score (rough scaling)
            energy_score = min(energy * 100, 10.0)

            # Combined
            score = (keyword_score * 0.4 + energy_score * 0.3 + laughter_score * 0.3)
            details.update({
                "keyword_score": keyword_score,
                "energy_score": energy_score,
                "laughter_score": laughter_score,
            })

            return AIResult(
                analyzer="audio_ai",
                score=min(score, 10.0),
                details=details,
                timestamp=time.time()
            )

        except Exception as e:
            return AIResult(
                analyzer="audio_ai",
                score=0.0,
                details={"error": str(e)},
                timestamp=time.time()
            )


class VisionAnalyzer(AIAnalyzerBase):
    """Visual analysis using vision LLM (OpenAI GPT-4V or compatible)."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str = "", enabled: bool = True, sample_interval: int = 5):
        super().__init__("visual_ai", enabled)
        self.model = model
        self.api_key = api_key
        self.sample_interval = sample_interval
        self._client = None

    def warmup(self):
        if not self.enabled or not self.api_key:
            if self.enabled:
                log("  Vision AI: no API key provided, disabled")
            self.enabled = False
            return
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
            log(f"  Vision AI ready: {self.model}")
        except ImportError:
            log("  OpenAI package not installed, vision AI disabled")
            self.enabled = False
        except Exception as e:
            log(f"  Vision AI init failed: {e}")
            self.enabled = False

    def analyze(self, segment_path: Path, context: dict) -> AIResult:
        if not self.enabled or not self._client:
            return AIResult(analyzer="visual_ai", score=0.0, details={"error": "not_loaded"})

        start = time.time()
        details = {}

        try:
            # Extract middle frame
            frame_path = self._extract_frame(segment_path)
            if not frame_path:
                return AIResult(analyzer="visual_ai", score=0.0, details={"error": "frame_extract_failed"})

            # Encode image
            import base64
            with open(frame_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

            # Analyze with vision model
            prompt = (
                "Rate 0-10: Is this frame a highlight moment from a live stream? Look for:\n"
                "- Big plays, wins, kills, clutch moments in games\n"
                "- Funny reactions, surprised/excited faces\n"
                "- Visual gags, glitches, Easter eggs\n"
                "- Achievement unlocks, level ups, victory screens\n"
                "- Streamer celebrating or reacting strongly\n"
                "Return only a number 0-10."
            )

            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                    ]
                }],
                max_tokens=10,
                temperature=0
            )

            text = response.choices[0].message.content.strip()
            try:
                score = float(text)
                score = max(0, min(10, score))
            except ValueError:
                import re as _re
                match = _re.search(r'(\d+(?:\.\d+)?)', text)
                score = float(match.group(1)) if match else 0.0

            details["frame_path"] = str(frame_path)
            details["raw_response"] = text

            # Clean up frame
            try:
                frame_path.unlink()
            except:
                pass

            return AIResult(
                analyzer="visual_ai",
                score=score,
                details=details,
                timestamp=time.time()
            )

        except Exception as e:
            return AIResult(
                analyzer="visual_ai",
                score=0.0,
                details={"error": str(e)},
                timestamp=time.time()
            )

    def _extract_frame(self, video_path: Path) -> Optional[Path]:
        """Extract a frame from the middle of the video segment."""
        import subprocess
        output_path = video_path.with_suffix(".jpg")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ss", "00:00:05",
            "-vframes", "1",
            "-q:v", "2",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return output_path
        return None


class ChatSentimentAnalyzer(AIAnalyzerBase):
    """Chat analysis: velocity, sentiment, emote density, keywords."""

    def __init__(self, enabled: bool = True, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment"):
        super().__init__("chat_ai", enabled)
        self.model_name = model_name
        self._pipeline = None
        self._message_buffer: List[dict] = []

    def warmup(self):
        if not self.enabled:
            return
        try:
            from transformers import pipeline
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                tokenizer=self.model_name,
                device=-1
            )
            log(f"  Chat sentiment model loaded: {self.model_name}")
        except ImportError:
            log("  Transformers not installed, chat sentiment disabled")
            self.enabled = False
        except Exception as e:
            log(f"  Chat sentiment load failed: {e}")
            self.enabled = False

    def add_message(self, timestamp: float, text: str, user: str = ""):
        """Add a chat message to the buffer."""
        self._message_buffer.append({
            "timestamp": timestamp,
            "text": text,
            "user": user
        })
        # Keep last 5 minutes
        cutoff = time.time() - 300
        self._message_buffer = [m for m in self._message_buffer if m["timestamp"] > cutoff]

    def analyze(self, segment_path: Path, context: dict) -> AIResult:
        if not self.enabled:
            return AIResult(analyzer="chat_ai", score=0.0, details={"disabled": True})

        start = time.time()
        details = {}

        try:
            segment_start = context.get("segment_start", time.time() - 10)
            segment_end = context.get("segment_end", time.time())

            # Filter messages in window
            window_messages = [
                m for m in self._message_buffer
                if segment_start <= m["timestamp"] <= segment_end
            ]

            if not window_messages:
                return AIResult(
                    analyzer="chat_ai",
                    score=0.0,
                    details={"message_count": 0},
                    timestamp=time.time()
                )

            # Velocity
            window_duration = segment_end - segment_start
            velocity = len(window_messages) / max(window_duration, 1)
            details["velocity"] = velocity
            details["message_count"] = len(window_messages)
            velocity_score = min(velocity / 50.0 * 10, 10.0)  # 50 msgs/sec = max

            # Sentiment
            sentiment_scores = {"positive": 0, "negative": 0, "neutral": 0}
            if self._pipeline:
                texts = [m.get("text", "") for m in window_messages if m.get("text")]
                if texts:
                    results = self._pipeline(texts[:50])
                    for r in results:
                        label = r["label"].lower()
                        if "pos" in label:
                            sentiment_scores["positive"] += 1
                        elif "neg" in label:
                            sentiment_scores["negative"] += 1
                        else:
                            sentiment_scores["neutral"] += 1

            details["sentiment"] = sentiment_scores
            total = sum(sentiment_scores.values())
            sentiment_score = 0.0
            if total > 0:
                sentiment_score = (sentiment_scores["positive"] / total) * 10

            # Emote density (uppercase words)
            emote_count = 0
            for m in window_messages:
                text = m.get("text", "")
                words = text.split()
                emote_count += sum(1 for w in words if w.isupper() and len(w) > 2)
            details["emote_count"] = emote_count
            emote_score = min(emote_count / max(len(window_messages), 1) * 20, 10.0)

            # Keywords
            keywords = ["clip it", "clippable", "highlight", "timestamp", "pog", "poggers"]
            keyword_matches = sum(
                1 for m in window_messages
                if any(kw in m.get("text", "").lower() for kw in keywords)
            )
            details["keyword_matches"] = keyword_matches
            keyword_score = min(keyword_matches * 2.0, 10.0)

            # Combined
            score = (velocity_score * 0.4 + sentiment_score * 0.2 +
                    emote_score * 0.2 + keyword_score * 0.2)
            details.update({
                "velocity_score": velocity_score,
                "sentiment_score": sentiment_score,
                "emote_score": emote_score,
                "keyword_score": keyword_score,
            })

            return AIResult(
                analyzer="chat_ai",
                score=min(score, 10.0),
                details=details,
                timestamp=time.time()
            )

        except Exception as e:
            return AIResult(
                analyzer="chat_ai",
                score=0.0,
                details={"error": str(e)},
                timestamp=time.time()
            )


class FusionScorer:
    """Combines multiple AI analyzer outputs into a single highlight score."""

    def __init__(self, threshold: float = 6.5, cooldown_seconds: int = 60):
        self.weights = {
            "audio_ai": 0.30,      # Whisper transcription + hype + laughter
            "visual_ai": 0.30,     # Vision model frame analysis
            "chat_ai": 0.25,       # Chat velocity + sentiment + emotes
            "audio_loudness": 0.10, # Existing RMS loudness
            "chat_spike": 0.05,    # Existing statistical spike
        }
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._last_clip_time: Dict[str, float] = {}
        self._clip_count = 0
        self._feedback_buffer: List[dict] = []

    def score(self, ai_results: List[AIResult], audio_loudness: float = 0,
              chat_spike_ratio: float = 0, channel_key: str = "") -> tuple:
        """Calculate fused highlight score. Returns (total_score, breakdown, should_clip)."""

        # Extract AI scores
        ai_scores = {r.analyzer: r.score for r in ai_results}

        # Normalize audio loudness to 0-10 scale (0 dB above normal = 0, 20 dB = 10)
        audio_loudness_norm = min(max(audio_loudness, 0) / 20.0 * 10, 10.0)

        # Normalize chat spike ratio to 0-10 (1x = 0, 5x = 10)
        chat_spike_norm = min(max(chat_spike_ratio - 1, 0) / 4.0 * 10, 10.0)

        # Weighted fusion
        breakdown = {}
        total = 0.0

        for key, weight in self.weights.items():
            if key == "audio_loudness":
                val = audio_loudness_norm
            elif key == "chat_spike":
                val = chat_spike_norm
            else:
                val = ai_scores.get(key, 0.0)

            weighted = val * weight
            breakdown[key] = weighted
            total += weighted

        # Check cooldown
        on_cooldown = False
        if channel_key:
            last = self._last_clip_time.get(channel_key, 0)
            on_cooldown = (time.time() - last) < self.cooldown_seconds

        should_clip = total >= self.threshold and not on_cooldown

        if should_clip and channel_key:
            self._last_clip_time[channel_key] = time.time()
            self._clip_count += 1

        return total, breakdown, should_clip

    def record_feedback(self, channel_key: str, score: float, breakdown: dict, approved: bool):
        """Record user feedback for learning."""
        self._feedback_buffer.append({
            "timestamp": time.time(),
            "channel": channel_key,
            "score": score,
            "breakdown": breakdown,
            "approved": approved
        })
        # Keep last 1000
        if len(self._feedback_buffer) > 1000:
            self._feedback_buffer = self._feedback_buffer[-1000:]

    def get_stats(self) -> dict:
        return {
            "total_clips": self._clip_count,
            "weights": self.weights,
            "threshold": self.threshold,
            "feedback_count": len(self._feedback_buffer),
        }


class SlidingWindowMedian:
    """Sliding window median using a sorted list. O(log n) insert, O(n) remove, O(1) median.
    For window sizes ~600 (5 min at 0.5s intervals), O(n) remove is very fast."""
    def __init__(self, window_seconds, resolution, min_readings=2):
        self.window_seconds = window_seconds
        self.resolution = resolution
        self.min_readings = min_readings
        self.data = []          # list of (value, timestamp), kept sorted by value
        self.by_time = []       # list of (timestamp, value), kept sorted by timestamp

    def add(self, timestamp, value):
        """Add a new reading. Removes expired entries."""
        # Remove expired entries (older than window_seconds)
        cutoff = timestamp - self.window_seconds
        while self.by_time and self.by_time[0][0] < cutoff:
            old_ts, old_val = self.by_time.pop(0)
            # Remove from sorted data list
            idx = bisect_left(self.data, (old_val, old_ts))
            # Find exact match (there could be duplicate values)
            while idx < len(self.data) and self.data[idx][0] == old_val:
                if self.data[idx][1] == old_ts:
                    self.data.pop(idx)
                    break
                idx += 1
        # Insert new entry (keep both lists sorted)
        insort(self.by_time, (timestamp, value))
        insort(self.data, (value, timestamp))

    def median(self):
        """Return median of current window, or None if insufficient data."""
        n = len(self.data)
        if n < self.min_readings:
            return None
        mid = n // 2
        if n % 2 == 0:
            return (self.data[mid - 1][0] + self.data[mid][0]) / 2.0
        return self.data[mid][0]

    def __len__(self):
        return len(self.data)


# Need bisect for SlidingWindowMedian
from bisect import bisect_left, insort


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)



def parse_source(text):                                                                              #responsible for figuring out if in the file i have given a twitch or yt link
    """Returns dict(site, name, url, link). name is safe to use as a folder name."""
    t = text.strip().strip('"')
    low = t.lower()
    if "youtube.com" in low or "youtu.be" in low:                                                    #detects YouTube links
        url = t if low.startswith("http") else "https://" + t   
        m_handle = re.search(r"youtube\.com/(@[\w.\-]+)", url, re.I)
        m_chan = re.search(r"youtube\.com/((?:channel|c|user)/[\w.\-]+)", url, re.I)
        m_video = re.search(r"(?:[?&]v=|youtu\.be/|/live/)([\w-]{11})", url)
        if m_handle:
            base = f"https://www.youtube.com/{m_handle.group(1)}"
            name, url = m_handle.group(1)[1:], base + "/live"
        elif m_chan:
            base = f"https://www.youtube.com/{m_chan.group(1)}"
            name, url = m_chan.group(1).split("/")[-1], base + "/live"
        elif m_video:
            base = url = f"https://www.youtube.com/watch?v={m_video.group(1)}"
            name = m_video.group(1)
        else:
            sys.exit(f"Couldn't understand that YouTube link: {text}\n"
                     f"Use the channel's live link, e.g. https://www.youtube.com/@Name/live")
        name = re.sub(r"[^\w.\-]", "_", name)
        return {"site": "youtube", "name": "youtube-" + name, "url": url, "link": base,
                "label": name}
    name = low.lstrip("#").rstrip("/").split("/")[-1].split("?")[0]
    if not re.fullmatch(r"\w{2,25}", name):                                                             #twitch channel link
        sys.exit(f"That doesn't look like a Twitch channel name: {text}")
    return {"site": "twitch", "name": name, "url": f"https://twitch.tv/{name}",
            "link": f"https://twitch.tv/{name}", "label": name}


def ytdlp_format(quality):
    """Map streamlink-style quality ('best', '720p60') to a yt-dlp format string."""
    if quality == "best":
        return "b"
    m = re.match(r"(\d+)p", quality)
    return f"b[height<={m.group(1)}]/b" if m else quality


# --------------------------------------------------------------------------
# 1. RECORD: streamlink -> ffmpeg, split into 10s files named by wall-clock time.
#    Naming segments by the time they arrived keeps chat and video in sync even
#    when Twitch ads or drops leave gaps, and lets us delete old footage so the
#    disk doesn't fill up over a long night.
# --------------------------------------------------------------------------
def list_segments(seg_dir):
    segs = []
    for p in seg_dir.glob("seg_*.ts"):
        m = SEG_RE.search(p.name)
        if m:
            t = dt.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").timestamp()
            segs.append((t, p))
    segs.sort()
    return segs


class Recorder(threading.Thread):
    def __init__(self, args, seg_dir):
        super().__init__(daemon=True)
        self.args = args
        self.seg_dir = seg_dir
        self.procs = []
        self.live_since = None

    def is_live(self):
        segs = list_segments(self.seg_dir)
        return bool(segs) and time.time() - segs[-1][1].stat().st_mtime < 30

    def prune(self):
        if self.args.buffer_minutes <= 0:
            return
        cutoff = time.time() - self.args.buffer_minutes * 60
        segs = list_segments(self.seg_dir)
        for t, p in segs[:-2]:
            if t < cutoff:
                try:
                    p.unlink()
                except OSError:
                    pass  # in use by a cut right now; try again next round

    def source_cmd(self):
        a = self.args
        if a.src["site"] == "twitch":
            # streamlink waits by itself until the channel goes live.
            return ["streamlink", a.src["url"], a.quality, "--stdout",
                    "--retry-streams", "30", "--retry-max", "0", "--loglevel", "warning"]
        # yt-dlp exits if the channel isn't live; run() just tries again in 30s.
        return ["yt-dlp", "-f", ytdlp_format(a.quality), "-o", "-", "--quiet", "--no-warnings",
                "--no-part", "--match-filters", "is_live", a.src["url"]]

    def run(self):
        a = self.args
        self.seg_dir.mkdir(parents=True, exist_ok=True)
        waiting_logged = False
        while not STOP.is_set():
            if not waiting_logged:
                log(f"Waiting for {a.src['link']} to go live (checks every 30s)...")
                waiting_logged = True
            sl = subprocess.Popen(self.source_cmd(), stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL if a.src["site"] == "youtube" else None)
            ff = subprocess.Popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-map", "0:v?", "-map", "0:a?", "-c", "copy",
                 "-f", "segment", "-segment_time", str(SEG_SECONDS),
                 # No -reset_timestamps: keeping the stream's own continuous timestamps lets
                 # cut_clip join segments back into one unbroken stream (keeps audio in sync).
                 "-segment_format", "mpegts", "-strftime", "1",
                 str(self.seg_dir / "seg_%Y%m%d-%H%M%S.ts")],
                stdin=sl.stdout)
            sl.stdout.close()
            self.procs = [sl, ff]
            announced = False
            while ff.poll() is None and not STOP.is_set():
                STOP.wait(5)
                if not announced and self.is_live():
                    log("LIVE! Recording started. Clips will be cut whenever chat spikes.")
                    announced = True
                    self.live_since = time.time()
                self.prune()
            self.kill()
            if STOP.is_set():
                break
            self.live_since = None
            if announced:
                log("Stream ended or dropped. Waiting for it to come back...")
                waiting_logged = False
            STOP.wait(10 if announced or a.src["site"] == "twitch" else 30)

    def kill(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()


# --------------------------------------------------------------------------
# 2. READ CHAT
#    Twitch:  anonymous read-only IRC (justinfan nick, no token).
#    YouTube: yt-dlp downloads the live chat to a file as it happens; we tail it.
# --------------------------------------------------------------------------
def write_chat(f, now, user, msg):
    f.write(f"{dt.datetime.fromtimestamp(now).isoformat(timespec='seconds')}\t{user}\t{msg}\n")
    f.flush()


class TwitchChat(threading.Thread):
    def __init__(self, channel, on_message, chat_log):
        super().__init__(daemon=True)
        self.channel = channel.lower()
        self.on_message = on_message
        self.chat_log = chat_log

    def run(self):
        while not STOP.is_set():
            try:
                self._session()
            except OSError as e:
                log(f"Chat connection lost ({e}); reconnecting in 5s.")
            STOP.wait(5)

    def _session(self):
        s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=60)
        nick = f"justinfan{random.randint(10000, 99999)}"
        s.sendall(f"NICK {nick}\r\nJOIN #{self.channel}\r\n".encode())
        log(f"Chat connected to #{self.channel} (read-only).")
        buf = b""
        with open(self.chat_log, "a", encoding="utf-8") as f:
            while not STOP.is_set():
                try:
                    data = s.recv(65536)
                except socket.timeout:
                    s.sendall(b"PING :tmi.twitch.tv\r\n")
                    continue
                if not data:
                    raise ConnectionError("server closed the connection")
                buf += data
                *lines, buf = buf.split(b"\r\n")
                for raw in lines:
                    line = raw.decode("utf-8", "replace")
                    if line.startswith("PING"):
                        s.sendall(("PONG" + line[4:] + "\r\n").encode())
                    elif " PRIVMSG #" in line and line.startswith(":"):
                        user = line[1:line.find("!")]
                        msg = line.split(" PRIVMSG #", 1)[1].split(" :", 1)[-1]
                        now = time.time()
                        write_chat(f, now, user, msg)
                        self.on_message(now, msg)


def youtube_messages(obj):
    """Yield (user, text) for every chat message inside one line of yt-dlp's live_chat.json."""
    if isinstance(obj, dict):
        r = obj.get("liveChatTextMessageRenderer") or obj.get("liveChatPaidMessageRenderer")
        if r:
            user = (r.get("authorName") or {}).get("simpleText", "")
            parts = []
            for run in (r.get("message") or {}).get("runs", []):
                if "text" in run:
                    parts.append(run["text"])
                elif "emoji" in run:
                    sc = run["emoji"].get("shortcuts") or [""]
                    parts.append(sc[0])
            yield user, "".join(parts)
            return
        for v in obj.values():
            yield from youtube_messages(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from youtube_messages(v)


class YouTubeChat(threading.Thread):
    def __init__(self, url, label, on_message, chat_log, work_dir):
        super().__init__(daemon=True)
        self.url = url
        self.label = label
        self.on_message = on_message
        self.chat_log = chat_log
        self.work_dir = work_dir
        self.proc = None

    def run(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        while not STOP.is_set():
            for old in self.work_dir.glob("chat*"):
                try:
                    old.unlink()
                except OSError:
                    pass
            self.proc = subprocess.Popen(
                ["yt-dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
                 "--no-part", "--quiet", "--no-warnings", "--match-filters", "is_live",
                 "-o", str(self.work_dir / "chat.%(ext)s"), self.url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            got_any = self._tail()
            if self.proc.poll() is None:
                self.proc.terminate()
            if got_any and not STOP.is_set():
                log("YouTube chat stopped (stream ended?). Checking again in 30s.")
            STOP.wait(30)

    def _tail(self):
        """Follow the chat file while yt-dlp is writing it. Returns True if chat came in."""
        f_in, got_any, buf = None, False, ""
        with open(self.chat_log, "a", encoding="utf-8") as f_out:
            while not STOP.is_set():
                if f_in is None:
                    files = sorted(self.work_dir.glob("chat*.live_chat.json*"))
                    if files:
                        f_in = open(files[0], "r", encoding="utf-8", errors="replace")
                        log(f"Chat connected to YouTube {self.label} (read-only).")
                    elif self.proc.poll() is not None:
                        return got_any
                    else:
                        STOP.wait(1)
                        continue
                chunk = f_in.read()
                if not chunk:
                    if self.proc.poll() is not None:
                        break
                    STOP.wait(0.5)
                    continue
                buf += chunk
                *lines, buf = buf.split("\n")
                now = time.time()
                for line in lines:
                    try:
                        data = json.loads(line)
                    except ValueError:
                        continue
                    for user, msg in youtube_messages(data):
                        got_any = True
                        write_chat(f_out, now, user, msg)
                        self.on_message(now, msg)
        if f_in:
            f_in.close()
        return got_any

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# --------------------------------------------------------------------------
#   measures rate of chat messages and finds spikes)
# --------------------------------------------------------------------------
class Detector:
    def __init__(self, bucket=10, window=300, threshold=1.8, min_msgs=5,        
                 cooldown=60, warmup=120):                                                                      #warmup is basically the time it takes to create the average message rate before it can start clipping
        self.bucket = bucket
        self.threshold = threshold
        self.min_msgs = min_msgs
        self.cooldown = cooldown
        self.warmup_buckets = warmup // bucket
        self.history = collections.deque(maxlen=window // bucket)
        self.lock = threading.Lock()
        self.cur_start = None
        self.cur_msgs = []
        self.last_spike = -1e18

    def add(self, ts, msg):
        with self.lock:
            if self.cur_start is None:
                self.cur_start = ts - ts % self.bucket
            self.cur_msgs.append(msg)

    def tick(self, now):
        """Close finished buckets. Returns a list of spikes (dicts)."""
        spikes = []
        with self.lock:
            if self.cur_start is None:
                return spikes
            while now >= self.cur_start + self.bucket:
                msgs, self.cur_msgs = self.cur_msgs, []
                start = self.cur_start
                self.cur_start += self.bucket
                count = len(msgs)
                if len(self.history) >= self.warmup_buckets:
                    baseline = sum(self.history) / len(self.history)
                    if (count >= self.min_msgs
                            and count >= self.threshold * max(baseline, 0.1)
                            and start - self.last_spike >= self.cooldown):
                        self.last_spike = start
                        spikes.append({"time": start, "count": count,
                                       "baseline": baseline, "top": top_messages(msgs)})
                self.history.append(count)
        return spikes


def top_messages(msgs, n=3):
    c = collections.Counter(m.strip().lower()[:40] for m in msgs if m.strip())
    return ", ".join(f"{m} x{k}" for m, k in c.most_common(n))


# --------------------------------------------------------------------------
# 3b. SOUND: measures how loud the stream is every half second, from the
#     10s buffer pieces. "Normal" = the median loudness of the last 5 minutes,
#     so a loud game or a loud streamer just raises the normal level.
#     Used to (1) line clips up with the actual moment, (2) rate clips,
#     (3) optionally skip chat spam during quiet moments, and (4) optionally
#     clip big sound spikes on their own (--audio-trigger).
# --------------------------------------------------------------------------
AUDIO_WIN = 0.5            # seconds per loudness reading
AUDIO_RATE = 8000          # samples per second we decode (plenty for loudness)


def measure_loudness(seg_path):
    """Loudness in dB (0 = max, -90 = silence) for every 0.5s of one segment, or None if no audio."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(seg_path),
                        "-map", "0:a:0", "-ac", "1", "-ar", str(AUDIO_RATE), "-f", "s16le", "-"],
                       capture_output=True)
    data = r.stdout
    if r.returncode != 0 or len(data) < 2:
        return None
    samples = array("h")
    samples.frombytes(data[: len(data) - len(data) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    n = int(AUDIO_RATE * AUDIO_WIN)
    levels = []
    for i in range(0, len(samples), n):
        chunk = samples[i:i + n]
        if len(chunk) < n // 2:
            break
        mean_sq = sum(x * x for x in chunk) / len(chunk)
        levels.append(max(10 * math.log10(mean_sq / 32768 ** 2), -90.0) if mean_sq > 0 else -90.0)
    return levels


class AudioMeter(threading.Thread):
    def __init__(self, seg_dir, on_loud=None, trigger_db=14.0):
        super().__init__(daemon=True)
        self.seg_dir = seg_dir
        self.on_loud = on_loud            # called as on_loud(time, db_above_normal) for --audio-trigger
        self.trigger_db = trigger_db
        # Sliding window median for 5-minute baseline (much faster than sorting deque)
        # Original required 2 min of data (120/AUDIO_WIN readings) before returning baseline
        min_readings = int(120 / AUDIO_WIN)
        self.baseline_window = SlidingWindowMedian(300, AUDIO_WIN, min_readings=min_readings)
        # Keep recent levels for peak() queries (last 20 minutes)
        self.levels = collections.deque(maxlen=int(20 * 60 / AUDIO_WIN))
        self.lock = threading.Lock()
        self.done = set()
        self.covered_until = 0.0
        self.has_audio = None             # None = don't know yet
        self.fails = 0
        self.last_trigger = -1e18

    def run(self):
        while not STOP.is_set():
            segs = list_segments(self.seg_dir)
            names = {p.name for _, p in segs}
            self.done &= names
            for t, p in segs[:-1]:        # the newest piece is still being written
                if p.name in self.done or STOP.is_set():
                    continue
                self.done.add(p.name)
                levels = measure_loudness(p)
                if levels is None:
                    self.fails += 1
                    if self.has_audio is None and self.fails >= 3:
                        self.has_audio = False
                        log("Sound: no audio found in this stream, so sound features are off.")
                    continue
                if not self.has_audio:
                    self.has_audio = True
                    log("Sound: audio detected. Sound tracking is on (needs ~2 min to learn normal volume).")
                new = [(t + i * AUDIO_WIN, db) for i, db in enumerate(levels)]
                with self.lock:
                    for ts, db in new:
                        self.levels.append((ts, db))
                        self.baseline_window.add(ts, db)
                    self.covered_until = max(self.covered_until, t + len(levels) * AUDIO_WIN)
                if self.on_loud:
                    self._check_trigger(new)
            STOP.wait(1)

    def baseline(self, at):
        """Median loudness of the 5 minutes before `at`, or None if we don't have 2 minutes yet."""
        with self.lock:
            # SlidingWindowMedian already maintains the 5-minute window
            return self.baseline_window.median()

    def peak(self, start, end):
        """(time, dB) of the loudest reading between start and end, or None."""
        with self.lock:
            window = [(t, db) for t, db in self.levels if start <= t <= end]
        return max(window, key=lambda x: x[1]) if window else None

    def wait_covered(self, until, timeout=25):
        deadline = time.time() + timeout
        while not STOP.is_set() and time.time() < deadline:
            if self.covered_until >= until or self.has_audio is False:
                return
            STOP.wait(1)

    def _check_trigger(self, new):
        # Needs 2 loud readings within 1.5s, so one clap or bang doesn't count.
        for i, (t, db) in enumerate(new):
            base = self.baseline(t)
            if base is None or db - base < self.trigger_db or t - self.last_trigger < 30:
                continue
            nxt = new[i + 1:i + 4]
            if any(d - base >= self.trigger_db for _, d in nxt):
                self.last_trigger = t
                self.on_loud(t, db - base)


def sound_label(rel, boost):
    if rel is None:
        return "unknown"
    if rel >= boost:
        return "LOUD"
    if rel >= boost / 2:
        return "a bit louder"
    return "quiet"


def rate_moment(chat_ratio, rel, args):
    """TOP / GOOD / OK, based on how strong the chat and sound reactions were."""
    points = 0
    if chat_ratio is not None:
        points += 1 + (chat_ratio >= 2 * args.threshold)
    if rel is not None and rel >= args.audio_boost:
        points += 1 + (rel >= 1.5 * args.audio_boost)
    return "TOP" if points >= 3 else "GOOD" if points == 2 else "OK"


# --------------------------------------------------------------------------
# 4. CUT: join the buffer segments covering [start, end] and stream-copy a clip.
# --------------------------------------------------------------------------
def cut_clip(seg_dir, start, end, out_path):
    segs = list_segments(seg_dir)
    chosen = []
    for i, (t, p) in enumerate(segs[:-1]):          # last segment is still being written
        if segs[i + 1][0] > start and t < end:
            chosen.append((t, p))
    if not chosen:
        return False
    first = chosen[0][0]
    offset = max(0.0, start - first)
    length = end - max(start, first)
    # The segments are pieces of one MPEG-TS stream, so the concat: protocol joins them
    # byte-for-byte into one continuous stream. -ss after -i decodes and trims exactly,
    # and re-encoding means the clip starts on that exact frame. Stream-copying (-c copy)
    # had to start on a keyframe and hid the difference with MP4 edit lists, which many
    # players and apps ignore, so the sound played ~2s off the picture.
    # Runs inside seg_dir with bare names: avoids "C:" in a concat: URL on Windows.
    src = "concat:" + "|".join(p.name for _, p in chosen)
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src, "-ss", f"{offset:.2f}", "-t", f"{length:.2f}",
         "-map", "0:v?", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-af", "aresample=async=1",
         "-movflags", "+faststart", str(out_path.resolve())],
        cwd=seg_dir)
    return r.returncode == 0 and out_path.exists()


def wait_for_footage(seg_dir, end, timeout=90):
    """Block until a segment that starts after `end` exists (so `end` is on disk)."""
    deadline = end + SEG_SECONDS + timeout
    while not STOP.is_set() and time.time() < deadline:
        segs = list_segments(seg_dir)
        if segs and segs[-1][0] >= end:
            return True
        STOP.wait(2)
    return False


# --------------------------------------------------------------------------
# 5. CAPTIONS (optional): whisper.cpp -> .srt -> burned-in copy.
# --------------------------------------------------------------------------
def caption_worker(args, q):
    while True:
        clip = q.get()
        if clip is None:
            return
        try:
            wav = clip.with_suffix(".wav")
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip),
                            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
            subprocess.run([args.whisper_bin, "-m", args.whisper_model, "-f", str(wav),
                            "-osrt", "-of", str(clip.with_suffix("")), "-np"],
                           check=True, stdout=subprocess.DEVNULL)
            wav.unlink(missing_ok=True)
            srt = clip.with_suffix(".srt")
            out = clip.with_name(clip.stem + "_captioned.mp4")
            # Run inside the clip folder with bare filenames: avoids Windows path escaping in -vf.
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", clip.name,
                            "-vf", f"subtitles={srt.name}:force_style='Fontsize=20,Outline=2'",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-c:a", "copy", out.name], check=True, cwd=clip.parent)
            log(f"  captioned: {out.name}")
        except (subprocess.CalledProcessError, OSError) as e:
            log(f"  captions failed for {clip.name}: {e}")


# --------------------------------------------------------------------------
# Glue
# --------------------------------------------------------------------------
def handle_moment(args, spike, seg_dir, out_root, caption_q, audio,
                  ai_analyzers=None, fusion_scorer=None):
    """spike: a chat spike from Detector, or a sound-only moment (spike['source'] == 'sound'),
       or an AI highlight (spike['source'] == 'ai')."""
    t = spike["time"]
    from_sound = spike.get("source") == "sound"
    from_ai = spike.get("source") == "ai"
    end = t + args.after
    lengths = sorted(args.lengths)
    if not wait_for_footage(seg_dir, end):
        log("  footage never arrived for that moment; skipped.")
        return

    # --- use the sound to find the real moment (chat reacts a few seconds late)
    rel = spike.get("audio_rel")
    if audio is not None and not from_sound:
        audio.wait_covered(t + 5)
        base = audio.baseline(t)
        pk = audio.peak(t - args.audio_lookback, t + 5) if base is not None else None
        if pk:
            rel = pk[1] - base
            if rel >= args.audio_boost:
                log(f"  sound: LOUD (+{rel:.0f} dB) at {dt.datetime.fromtimestamp(pk[0]):%H:%M:%S}, "
                    f"lining the clip up with that moment.")
                t, end = pk[0], pk[0] + args.after
                if not wait_for_footage(seg_dir, end):
                    log("  footage never arrived for that moment; skipped.")
                    return
            else:
                log(f"  sound: {sound_label(rel, args.audio_boost)} (+{max(rel, 0):.0f} dB), "
                    f"using chat timing.")
                if args.skip_quiet and rel < args.audio_boost / 2:
                    log("  skipped: chat spiked but the stream stayed quiet (probably spam). "
                        "Turn off --skip-quiet to keep these.")
                    return

    chat_ratio = None if from_sound else spike["count"] / max(spike["baseline"], 0.1)

    # AI-enhanced rating
    if from_ai and spike.get("ai_score"):
        ai_score = spike["ai_score"]
        # Combine AI score with existing rating logic
        rating = "TOP" if ai_score >= 8 else "GOOD" if ai_score >= 6 else "OK"
        trigger = f"AI {ai_score:.1f}"
        sound_txt = f"AI score: {ai_score:.1f}/10"
        if rel is not None:
            sound_txt += f" | sound: {sound_label(rel, args.audio_boost)} (+{max(rel, 0):.0f} dB)"
    else:
        rating = rate_moment(chat_ratio, rel, args)
        trigger = "sound only" if from_sound else f"chat {chat_ratio:.0f}x"
        sound_txt = sound_label(rel, args.audio_boost) + (f" (+{max(rel, 0):.0f} dB)" if rel is not None else "")

    when = dt.datetime.fromtimestamp(t)
    day_dir = out_root / when.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    stem = when.strftime("%H%M%S")
    made = []
    for L in lengths:
        out = day_dir / f"{stem}_{L}s.mp4"
        if cut_clip(seg_dir, end - L, end, out):
            made.append(out)
            if caption_q is not None:
                caption_q.put(out)
        else:
            log(f"  could not cut {out.name}")
    if not made:
        log("  no clip saved for that moment (see the errors above).")
        return
    stats = getattr(args, "stats", None)
    if stats is not None:
        stats["moments"] += 1
        stats["files"] += len(made)
        stats["last_clip"] = when.strftime("%H:%M:%S")
    sizes = sum(p.stat().st_size for p in made) / 1e6
    log(f"CLIP SAVED {when:%H:%M:%S} [{rating}] {trigger}, sound {sound_txt}: "
        f"{', '.join(p.stem.split('_')[-1] for p in made)} ({sizes:.0f} MB) -> {day_dir}")

    # Generate AI title and description if available
    ai_title = ""
    ai_description = ""
    ai_breakdown = spike.get("ai_breakdown", {})
    if from_ai and ai_breakdown:
        ai_title = generate_ai_title(spike.get("ai_results", []), ai_breakdown, args.src.get("label", ""))
        ai_description = generate_ai_description(spike.get("ai_results", []), ai_breakdown,
                                                  args.src.get("label", ""), when)

    # Write enhanced credit file
    credit_lines = [
        f"Clipped from {args.src['label']}'s live stream on {args.src['site'].capitalize()}: "
        f"{args.src['link']}\n",
        f"Streamed {when:%Y-%m-%d at %H:%M:%S}. Credit and link the streamer when posting.\n",
        f"Rating: {rating} | trigger: {trigger} | sound: {sound_txt}\n",
        f"Chat at that moment: {spike.get('top') or '-'}\n",
    ]
    if ai_title:
        credit_lines.append(f"AI Title: {ai_title}\n")
    if ai_description:
        credit_lines.append(f"AI Description: {ai_description}\n")
    if ai_breakdown:
        credit_lines.append(f"AI Score Breakdown: {json.dumps(ai_breakdown, indent=2)}\n")

    (day_dir / f"{stem}_credit.txt").write_text("".join(credit_lines), encoding="utf-8")

    # Write metadata JSON for AI clips
    if from_ai:
        meta = {
            "timestamp": when.isoformat(),
            "platform": args.src["site"],
            "channel": args.src["name"],
            "title": ai_title,
            "description": ai_description,
            "rating": rating,
            "trigger": trigger,
            "ai_score": spike.get("ai_score"),
            "ai_breakdown": ai_breakdown,
            "clip_files": [str(p.relative_to(out_root)) for p in made],
            "duration_seconds": max(lengths),
        }
        (day_dir / f"{stem}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Update CSV with AI info
    header = ["time", "rating", "trigger", "chat_ratio", "msgs_in_10s", "avg_msgs_per_10s",
              "sound", "sound_db_above_normal", "top_chat", "files", "ai_score", "ai_trigger"]
    index = out_root / "clips.csv"
    if index.exists():
        with open(index, encoding="utf-8") as f:
            if f.readline().strip() != ",".join(header):
                f.close()
                index.replace(index.with_name("clips_old.csv"))
    new = not index.exists()
    with open(index, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        ai_score_val = spike.get("ai_score", "")
        ai_trigger = "ai" if from_ai else ("sound" if from_sound else "chat")
        w.writerow([when.isoformat(timespec="seconds"), rating, ai_trigger,
                    "" if chat_ratio is None else f"{chat_ratio:.1f}",
                    spike.get("count", ""), "" if from_sound else f"{spike['baseline']:.1f}",
                    sound_label(rel, args.audio_boost), "" if rel is None else f"{rel:.1f}",
                    spike.get("top", ""), " ".join(str(p.relative_to(out_root)) for p in made),
                    "" if ai_score_val == "" else f"{ai_score_val:.1f}", ai_trigger])


def generate_ai_title(ai_results, breakdown, streamer_label):
    """Generate a smart title from AI analysis results."""
    # Find top contributing factors
    sorted_factors = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    top_factors = [f[0] for f in sorted_factors[:3] if f[1] > 0.5]

    factor_labels = {
        "audio_ai": "Epic Quote",
        "visual_ai": "Visual Highlight",
        "chat_ai": "Chat Explosion",
        "audio_loudness": "Loud Moment",
        "chat_spike": "Chat Spike",
    }

    labels = [factor_labels.get(f, f.replace("_", " ").title()) for f in top_factors]

    if labels:
        return f"[{', '.join(labels)}] {streamer_label}"
    else:
        return f"[AI Highlight] {streamer_label}"


def generate_ai_description(ai_results, breakdown, streamer_label, when):
    """Generate a description with AI score breakdown."""
    lines = [
        f"AI-detected highlight from {streamer_label}'s stream",
        f"Detected at {when:%H:%M:%S}",
        "",
        "AI Score Breakdown:",
    ]

    for factor, value in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
        if value > 0:
            bar = "█" * int(value * 2)
            label = factor.replace("_", " ").title()
            lines.append(f"  {label}: {value:.2f} {bar}")

    lines.extend([
        "",
        "Generated by Clip Watcher AI 🤖",
    ])

    return "\n".join(lines)


def check_tools(args, sites):
    needed = ["ffmpeg"]
    if "twitch" in sites:
        needed.append("streamlink")
    if "youtube" in sites:
        needed.append("yt-dlp")
    missing = [t for t in needed if not shutil.which(t)]
    if args.captions:
        if not shutil.which(args.whisper_bin):
            missing.append(args.whisper_bin)
        if not args.whisper_model or not Path(args.whisper_model).exists():
            sys.exit(f"--captions needs --whisper-model pointing at a ggml model file "
                     f"(got: {args.whisper_model!r}).")
    if missing:
        sys.exit("Missing programs: " + ", ".join(missing) +
                 "\nInstall them (SETUP GUIDE.txt, Part 2), then open a NEW window and try again.")


def fmt_dur(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


# --------------------------------------------------------------------------
# One channel (this is what each watcher process runs)
# --------------------------------------------------------------------------
def run_one(args):
    args.src = parse_source(args.channel)
    check_tools(args, {args.src["site"]})

    out_root = Path(args.out) / args.src["name"]
    seg_dir = out_root / "_buffer"
    out_root.mkdir(parents=True, exist_ok=True)
    args.stats = {"chat": 0, "moments": 0, "files": 0, "last_clip": None}

    det = Detector(threshold=args.threshold, min_msgs=args.min_msgs, cooldown=args.cooldown)

    # --- AI Analyzers ---
    ai_analyzers = []
    chat_ai = None
    fusion_scorer = None

    if getattr(args, "ai_enabled", False):
        log("  Initializing AI analyzers...")

        # Audio AI (Whisper)
        if getattr(args, "ai_audio", True):
            audio_ai = WhisperAudioAnalyzer(
                model_name=getattr(args, "ai_whisper_model", "base"),
                device=getattr(args, "ai_device", "auto"),
                enabled=True
            )
            audio_ai.warmup()
            if audio_ai.enabled:
                ai_analyzers.append(audio_ai)
                log(f"  Audio AI: Whisper {args.ai_whisper_model} ready")

        # Visual AI (Vision LLM)
        if getattr(args, "ai_visual", False) and getattr(args, "ai_vision_key", ""):
            visual_ai = VisionAnalyzer(
                model=getattr(args, "ai_vision_model", "gpt-4o-mini"),
                api_key=args.ai_vision_key,
                enabled=True,
                sample_interval=getattr(args, "ai_vision_interval", 5)
            )
            visual_ai.warmup()
            if visual_ai.enabled:
                ai_analyzers.append(visual_ai)
                log(f"  Visual AI: {args.ai_vision_model} ready")

        # Chat Sentiment AI
        if getattr(args, "ai_chat", True):
            chat_ai = ChatSentimentAnalyzer(
                enabled=True,
                model_name=getattr(args, "ai_chat_model", "cardiffnlp/twitter-roberta-base-sentiment")
            )
            chat_ai.warmup()
            if chat_ai.enabled:
                ai_analyzers.append(chat_ai)
                log(f"  Chat AI: sentiment analysis ready")

        # Fusion Scorer
        fusion_scorer = FusionScorer(
            threshold=getattr(args, "ai_threshold", 6.5),
            cooldown_seconds=args.cooldown
        )

        if ai_analyzers:
            log(f"  AI analyzers ready: {[a.name for a in ai_analyzers]}")
        else:
            log("  No AI analyzers enabled, falling back to chat/spike detection only")

    def on_message(ts, msg):
        args.stats["chat"] += 1
        det.add(ts, msg)
        # Also feed chat AI
        if chat_ai:
            chat_ai.add_message(ts, msg)

    rec = Recorder(args, seg_dir)
    if args.src["site"] == "twitch":
        chat = TwitchChat(args.src["name"], on_message, out_root / "chat.log")
    else:
        chat = YouTubeChat(args.src["url"], args.src["label"], on_message,
                           out_root / "chat.log", out_root / "_chat_tmp")
    caption_q = None
    if args.captions:
        caption_q = queue.Queue()
        threading.Thread(target=caption_worker, args=(args, caption_q), daemon=True).start()

    # One shared list of clipped moments, so chat and sound never clip the same moment twice.
    moments, moments_lock = [], threading.Lock()

    def claim(approx_time):
        with moments_lock:
            if any(abs(approx_time - m) < args.cooldown for m in moments):
                return False
            moments.append(approx_time)
            del moments[:-50]
            return True

    def on_loud(t, rel):                       # only used with --audio-trigger
        if not rec.is_live() or not claim(t):
            return
        log(f"SOUND SPIKE! +{rel:.0f} dB above normal at {dt.datetime.fromtimestamp(t):%H:%M:%S}")
        log("  cutting clips...")
        threading.Thread(target=handle_moment,
                         args=(args, {"time": t, "source": "sound", "audio_rel": rel},
                               seg_dir, out_root, caption_q, audio, ai_analyzers, fusion_scorer),
                         daemon=True).start()

    audio = None
    if not args.no_audio:
        audio = AudioMeter(seg_dir, on_loud if args.audio_trigger else None, args.audio_trigger_db)

    channel_key = f"{args.src['site']}/{args.src['name']}"

    log(f"Watching {args.src['link']} ({args.src['site'].capitalize()})")
    log(f"  clips: {', '.join(f'{L}s' for L in sorted(args.lengths))}  ->  {out_root.resolve()}")
    log("  sound: " + ("off (--no-audio)" if audio is None else
                       "used to time and rate clips" + (", and clips big sound spikes on its own"
                                                        if args.audio_trigger else "")))
    if ai_analyzers:
        log(f"  AI: {', '.join([a.name for a in ai_analyzers])} (threshold={fusion_scorer.threshold})")
    log(f"  a status update prints every {args.status_minutes} min. Ctrl+C stops it.")
    rec.start()
    chat.start()
    if audio is not None:
        audio.start()

    # AI Analysis loop state
    last_ai_check = time.time()
    ai_check_interval = getattr(args, "ai_check_interval", 30)  # seconds
    analyzed_segments = set()  # track which segments we've analyzed

    last_status, chat_at_last = time.time(), 0
    next_status = time.time() + args.status_minutes * 60
    try:
        while True:
            now = time.time()

            # --- AI Analysis Loop ---
            if ai_analyzers and fusion_scorer and now - last_ai_check >= ai_check_interval:
                last_ai_check = now
                # Run AI analysis in background thread to not block main loop
                threading.Thread(
                    target=run_ai_analysis,
                    args=(args, seg_dir, out_root, caption_q, audio,
                          ai_analyzers, fusion_scorer, channel_key,
                          analyzed_segments, claim),
                    daemon=True
                ).start()

            # --- Original Chat Spike Detection ---
            for spike in det.tick(now):
                ratio = spike["count"] / max(spike["baseline"], 0.1)
                live = rec.is_live()
                log(f"SPIKE! {spike['count']} msgs in 10s (normal is {spike['baseline']:.1f}, "
                    f"{ratio:.0f}x) | chat: {spike['top']}")
                if not live:
                    log("  no clip: the stream isn't being recorded right now.")
                elif not claim(spike["time"] - 5):
                    log("  already clipped this moment (from the sound spike).")
                else:
                    log(f"  cutting clips... (waiting ~{int(args.after) + SEG_SECONDS}s "
                        f"for the footage after the moment)")
                    threading.Thread(target=handle_moment,
                                     args=(args, spike, seg_dir, out_root, caption_q, audio,
                                           ai_analyzers, fusion_scorer),
                                     daemon=True).start()
            if now >= next_status:
                s = args.stats
                per_min = (s["chat"] - chat_at_last) / max((now - last_status) / 60, 0.01)
                state = (f"LIVE for {fmt_dur(now - rec.live_since)}" if rec.live_since
                         else "offline, waiting for the stream")
                last = f" | last clip {s['last_clip']}" if s["last_clip"] else ""
                log(f"STATUS | {state} | chat {per_min:.0f} msgs/min | "
                    f"{s['moments']} moment{'' if s['moments'] == 1 else 's'} clipped "
                    f"({s['files']} files){last}")
                last_status, chat_at_last = now, s["chat"]
                next_status = now + args.status_minutes * 60
            time.sleep(1)
    except KeyboardInterrupt:
        log("Stopping...")
    finally:
        STOP.set()
        rec.kill()
        if hasattr(chat, "kill"):
            chat.kill()


def run_ai_analysis(args, seg_dir, out_root, caption_q, audio,
                    ai_analyzers, fusion_scorer, channel_key,
                    analyzed_segments, claim):
    """Background thread: analyze recent segments with AI and create clips for highlights."""
    try:
        # Get recent segments (last 60 seconds)
        segs = list_segments(seg_dir)
        if not segs:
            return

        # Analyze segments we haven't seen yet (last 60s worth)
        cutoff = time.time() - 60
        new_segments = [(t, p) for t, p in segs if t >= cutoff and p.name not in analyzed_segments]

        if not new_segments:
            return

        for seg_time, seg_path in new_segments:
            analyzed_segments.add(seg_path.name)
            # Keep analyzed_segments bounded
            if len(analyzed_segments) > 500:
                analyzed_segments.clear()

            # Prepare context for analyzers
            context = {
                "segment_start": seg_time,
                "segment_end": seg_time + SEG_SECONDS,
            }

            # Run all AI analyzers
            ai_results = []
            for analyzer in ai_analyzers:
                try:
                    result = analyzer.analyze(seg_path, context)
                    ai_results.append(result)
                except Exception as e:
                    log(f"  AI {analyzer.name} error: {e}")

            if not ai_results:
                continue

            # Get audio loudness for this segment
            audio_loudness = 0
            chat_spike_ratio = 0
            if audio is not None:
                audio.wait_covered(seg_time + SEG_SECONDS)
                base = audio.baseline(seg_time)
                pk = audio.peak(seg_time, seg_time + SEG_SECONDS)
                if base is not None and pk:
                    audio_loudness = pk[1] - base

            # Score with fusion scorer
            total_score, breakdown, should_clip = fusion_scorer.score(
                ai_results, audio_loudness, chat_spike_ratio, channel_key
            )

            # Log AI scores
            log(f"  AI Score: {total_score:.1f}/10 ({', '.join(f'{k}:{v:.1f}' for k,v in breakdown.items())})")

            if should_clip and claim(seg_time):
                # Create a synthetic spike for handle_moment
                spike = {
                    "time": seg_time,
                    "count": 0,
                    "baseline": 0,
                    "top": "AI highlight",
                    "source": "ai",
                    "audio_rel": audio_loudness,
                    "ai_score": total_score,
                    "ai_breakdown": breakdown,
                    "ai_results": ai_results
                }
                log(f"  AI HIGHLIGHT! Score: {total_score:.1f} -> cutting clips...")
                handle_moment(args, spike, seg_dir, out_root, caption_q, audio,
                             ai_analyzers, fusion_scorer)

    except Exception as e:
        log(f"  AI analysis error: {e}")


# --------------------------------------------------------------------------
# Everyone in channels.txt, in one window (used when no channel is given)
# --------------------------------------------------------------------------
COLORS = ["\033[96m", "\033[93m", "\033[95m", "\033[92m", "\033[94m", "\033[91m"]
RESET = "\033[0m"
PRINT_LOCK = threading.Lock()


def pause_on_windows():
    """Keep a double-clicked window open long enough to read it."""
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress Enter to close this window.")
        except (EOFError, KeyboardInterrupt):
            pass


def read_channels(path):
    entries = []
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(line.split()[0])
    return entries


def run_all(args, option_argv):
    if os.name == "nt":
        os.system("")                      # turns on colours in older Windows consoles
    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    path = Path(args.channels_file)
    if not path.is_absolute() and not path.exists():
        path = SCRIPT_DIR / path
    if not path.exists():
        print(f"Can't find {path}.\nCreate it with one Twitch name or YouTube link per line.")
        pause_on_windows()
        return

    sources, seen = [], set()
    for entry in read_channels(path):
        try:
            src = parse_source(entry)
        except SystemExit as e:
            print(f"Skipping a line in {path.name}: {e}")
            continue
        if src["name"] not in seen:
            seen.add(src["name"])
            sources.append((entry, src))
    if not sources:
        print(f"No channels to watch in {path}.\n"
              f"Open it in Notepad and add one Twitch name or YouTube link per line.\n"
              f"Lines starting with # are ignored, so remove the # from the ones you want.")
        pause_on_windows()
        return
    try:
        check_tools(args, {s["site"] for _, s in sources})
    except SystemExit as e:
        print(e)
        pause_on_windows()
        return

    width = max(len(s["label"]) for _, s in sources)
    labels = {s["name"]: s["label"] for _, s in sources}
    tag = {}
    for i, (_, s) in enumerate(sources):
        label = s["label"].ljust(width)
        tag[s["name"]] = f"{COLORS[i % len(COLORS)]}{label}{RESET}" if color else label

    def say(name, text):
        with PRINT_LOCK:
            print(f"{tag[name]} | {text}", flush=True)

    bar = "=" * 64
    print(bar)
    print(" CLIP WATCHER")
    print(f" Watching {len(sources)} channel{'s' if len(sources) != 1 else ''} from {path.name}:")
    for _, s in sources:
        print(f"   {s['label'].ljust(width)}  {s['site'].capitalize():8} {s['link']}")
    print(f" Clip lengths: {', '.join(f'{L}s' for L in sorted(args.lengths))}")
    print(f" Clips folder: {Path(args.out).resolve()}")
    print(" Every line starts with the channel it's about.")
    print(" Leave this window open. Press Ctrl+C to stop everything.")
    print(bar, flush=True)

    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    procs, pending, saved = {}, {}, collections.Counter()

    def pump(name, pipe):
        for raw in pipe:
            text = raw.decode("utf-8", "replace").rstrip()
            if text:
                if "CLIP SAVED" in text:
                    saved[name] += 1
                say(name, text)

    def launch(entry, src):
        p = subprocess.Popen([sys.executable, "-u", str(SCRIPT_DIR / "clipwatcher.py"), entry]
                             + option_argv,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=SCRIPT_DIR)
        threading.Thread(target=pump, args=(src["name"], p.stdout), daemon=True).start()
        procs[src["name"]] = {"p": p, "started": time.time(), "entry": entry, "src": src}

    for entry, src in sources:
        launch(entry, src)

    try:
        while procs or pending:
            now = time.time()
            for name, info in list(procs.items()):
                code = info["p"].poll()
                if code is None:
                    continue
                del procs[name]
                if now - info["started"] < 20:
                    say(name, "stopped right after starting (see the message above). Not restarting it.")
                else:
                    say(name, f"watcher stopped unexpectedly (code {code}). Restarting in 30s.")
                    pending[name] = (now + 30, info["entry"], info["src"])
            for name, (at, entry, src) in list(pending.items()):
                if now >= at:
                    del pending[name]
                    say(name, "restarting watcher.")
                    launch(entry, src)
            time.sleep(1)
        print("No watchers are running any more.")
    except KeyboardInterrupt:
        print("\nStopping all watchers (this takes a few seconds)...", flush=True)
    finally:
        for info in procs.values():
            try:
                info["p"].wait(15)
            except subprocess.TimeoutExpired:
                info["p"].terminate()
            except KeyboardInterrupt:
                info["p"].terminate()
        total = sum(saved.values())
        print(f"\nDone. {total} moment{'s' if total != 1 else ''} clipped this session"
              + (": " + ", ".join(f"{labels[name]} {n}" for name, n in saved.items()) if total else ".")
              + f"\nYour clips are in {Path(args.out).resolve()}")
    pause_on_windows()


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(
        description="Auto-clip Twitch or YouTube live streams where chat spikes. "
                    "With no channel given, watches everyone in channels.txt.")
    ap.add_argument("channel", nargs="?",
                    help="Twitch name (e.g. xqc) or YouTube link. Leave out to use channels.txt")
    ap.add_argument("--channels-file", default="channels.txt",
                    help="list of channels used when no channel is given (default channels.txt)")
    ap.add_argument("--lengths", default="45",
                    help="clip lengths in seconds, comma separated (default 45)")
    ap.add_argument("--after", type=float, default=15,
                    help="seconds of footage kept AFTER the chat spike; every clip ends here (default 15)")
    ap.add_argument("--quality", default="best", help="video quality, e.g. best, 1080p60, 720p60")
    ap.add_argument("--threshold", type=float, default=2.0,
                    help="spike = this many times the 5-minute average (default 2)")
    ap.add_argument("--min-msgs", type=int, default=5,
                    help="ignore spikes with fewer messages than this in 10s (default 5)")
    ap.add_argument("--cooldown", type=int, default=60, help="min seconds between clips (default 60)")
    ap.add_argument("--buffer-minutes", type=int, default=10,
                    help="minutes of raw footage kept on disk; 0 = keep everything (default 10)")
    ap.add_argument("--status-minutes", type=float, default=2,
                    help="how often each channel prints a status line (default 2)")
    ap.add_argument("--out", default=str(SCRIPT_DIR / "clips"),
                    help="output folder (default: the clips folder next to this script)")
    ap.add_argument("--no-audio", action="store_true",
                    help="don't use the stream's sound at all (chat only, like older versions)")
    ap.add_argument("--audio-boost", type=float, default=8,
                    help="dB above normal volume that counts as LOUD (default 8)")
    ap.add_argument("--audio-lookback", type=float, default=20,
                    help="seconds before a chat spike to search for the loud moment (default 20)")
    ap.add_argument("--skip-quiet", action="store_true",
                    help="skip chat spikes when the stream stayed quiet (filters spam, may miss calm jokes)")
    ap.add_argument("--audio-trigger", action="store_true",
                    help="also clip big sound spikes that chat didn't react to (good for small chats)")
    ap.add_argument("--audio-trigger-db", type=float, default=14,
                    help="how loud above normal a sound-only clip must be (default 14)")
    ap.add_argument("--captions", action="store_true", help="transcribe and burn in captions")
    ap.add_argument("--whisper-bin", default="whisper-cli", help="whisper.cpp binary (default whisper-cli)")
    ap.add_argument("--whisper-model", help="path to e.g. models/ggml-small.en.bin")

    # --- AI Highlight Detection ---
    ap.add_argument("--ai", action="store_true", dest="ai_enabled",
                    help="enable AI highlight detection (Whisper + optional Vision + Chat sentiment)")
    ap.add_argument("--ai-audio", action="store_true", default=True, dest="ai_audio",
                    help="enable Whisper audio transcription analysis (default: on with --ai)")
    ap.add_argument("--no-ai-audio", action="store_false", dest="ai_audio",
                    help="disable Whisper audio analysis")
    ap.add_argument("--ai-whisper-model", default="base",
                    help="Whisper model: tiny, base, small, medium, large (default: base)")
    ap.add_argument("--ai-device", default="auto",
                    help="device for Whisper: auto, cpu, cuda, mps (default: auto)")
    ap.add_argument("--ai-visual", action="store_true", dest="ai_visual",
                    help="enable visual analysis with vision LLM (requires --ai-vision-key)")
    ap.add_argument("--ai-vision-key", default="",
                    help="OpenAI API key for GPT-4V vision analysis")
    ap.add_argument("--ai-vision-model", default="gpt-4o-mini",
                    help="Vision model: gpt-4o-mini, gpt-4o, gpt-4-turbo (default: gpt-4o-mini)")
    ap.add_argument("--ai-vision-interval", type=int, default=5,
                    help="analyze 1 frame every N seconds (default: 5)")
    ap.add_argument("--ai-chat", action="store_true", default=True, dest="ai_chat",
                    help="enable chat sentiment analysis (default: on with --ai)")
    ap.add_argument("--no-ai-chat", action="store_false", dest="ai_chat",
                    help="disable chat sentiment analysis")
    ap.add_argument("--ai-chat-model", default="cardiffnlp/twitter-roberta-base-sentiment",
                    help="HuggingFace model for chat sentiment (default: twitter-roberta-base-sentiment)")
    ap.add_argument("--ai-threshold", type=float, default=6.5,
                    help="AI fusion score threshold 0-10 to auto-clip (default: 6.5)")
    ap.add_argument("--ai-check-interval", type=int, default=30,
                    help="seconds between AI analysis passes (default: 30)")

    args = ap.parse_args()
    args.lengths = [int(x) for x in args.lengths.split(",") if x.strip()]
    if args.channel:
        run_one(args)
    else:
        run_all(args, sys.argv[1:])


if __name__ == "__main__":
    main()
