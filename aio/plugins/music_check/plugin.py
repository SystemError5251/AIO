"""Musik-Check: inspects the audio of a clip before upload.

Offline: audio track present?, codec, loudness (LUFS), true peak, compared with
the -14 LUFS that Reels/Shorts/TikTok normalise to. Can write a loudness-
corrected copy. Optional online step: identify the music via AcoustID
(needs `fpcalc` from chromaprint and a free API key), to spot copyrighted songs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import media

TARGET_LUFS = -14.0
TOLERANCE_LU = 2.0
MAX_TRUE_PEAK = -1.0
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"


@dataclass
class Loudness:
    integrated: float  # LUFS, -inf for silence
    true_peak: float   # dBTP
    lra: float         # LU
    threshold: float


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def parse_loudnorm(stderr: str) -> Loudness:
    """Extract the JSON block that loudnorm prints at the end of ffmpeg's log."""
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not match:
        raise RuntimeError("loudnorm returned no measurement")
    data = json.loads(match.group(0))
    return Loudness(_num(data["input_i"]), _num(data["input_tp"]),
                    _num(data["input_lra"]), _num(data["input_thresh"]))


def measure(path: Path) -> Loudness:
    result = media.ffmpeg(["-i", str(path), "-vn", "-af",
                           f"loudnorm=I={TARGET_LUFS}:TP={MAX_TRUE_PEAK}:LRA=11:print_format=json",
                           "-f", "null", "-"])
    return parse_loudnorm(result.stderr)


def verdict(loud: Loudness) -> list[str]:
    """Translation keys describing the result."""
    if loud.integrated == float("-inf") or loud.integrated < -70:
        return ["music_check.silent"]
    notes = []
    if loud.integrated < TARGET_LUFS - TOLERANCE_LU:
        notes.append("music_check.too_quiet")
    elif loud.integrated > TARGET_LUFS + TOLERANCE_LU:
        notes.append("music_check.too_loud")
    else:
        notes.append("music_check.loudness_ok")
    if loud.true_peak > MAX_TRUE_PEAK:
        notes.append("music_check.peak_high")
    return notes


def normalize(path: Path, loud: Loudness, has_video: bool) -> Path:
    """Second loudnorm pass with the measured values (accurate, linear)."""
    out = media.output_path(path, "loudnorm", ".mp4" if has_video else ".m4a")
    filt = (f"loudnorm=I={TARGET_LUFS}:TP={MAX_TRUE_PEAK}:LRA=11:"
            f"measured_I={loud.integrated}:measured_TP={loud.true_peak}:"
            f"measured_LRA={loud.lra}:measured_thresh={loud.threshold}:linear=true")
    args = ["-y", "-i", str(path), "-map", "0:v?", "-map", "0:a:0", "-af", filt,
            "-ar", "48000", "-c:a", "aac", "-b:a", "192k"]
    if has_video:
        args += ["-c:v", "copy", "-movflags", "+faststart"]
    media.ffmpeg([*args, str(out)])
    return out


# --------------------------------------------------------------------------- #
# AcoustID (optional, online)
# --------------------------------------------------------------------------- #

def acoustid_key(ctx) -> str | None:
    return os.environ.get("AIO_ACOUSTID_KEY") or ctx.config.get("acoustid_key") or None


def fingerprint(path: Path) -> tuple[int, str]:
    result = subprocess.run([media.require("fpcalc"), "-json", "-length", "120", str(path)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "fpcalc failed")
    data = json.loads(result.stdout)
    return int(float(data["duration"])), data["fingerprint"]


def parse_acoustid(data: dict[str, Any], min_score: float = 0.5) -> list[tuple[float, str, str]]:
    """[(score, title, artists)] best first."""
    if data.get("status") != "ok":
        raise RuntimeError(data.get("error", {}).get("message", "AcoustID error"))
    matches = []
    for result in data.get("results", []):
        score = float(result.get("score", 0))
        if score < min_score:
            continue
        for rec in result.get("recordings", []) or []:
            title = rec.get("title")
            if not title:
                continue
            artists = ", ".join(a.get("name", "") for a in rec.get("artists", []) or [])
            matches.append((score, title, artists))
    matches.sort(key=lambda m: -m[0])
    seen, unique = set(), []
    for m in matches:
        if (m[1], m[2]) not in seen:
            seen.add((m[1], m[2]))
            unique.append(m)
    return unique


def identify(path: Path, key: str) -> list[tuple[float, str, str]]:
    duration, fp = fingerprint(path)
    body = urllib.parse.urlencode({"client": key, "duration": duration,
                                   "fingerprint": fp, "meta": "recordings"}).encode()
    with urllib.request.urlopen(urllib.request.Request(ACOUSTID_URL, data=body), timeout=20) as resp:
        return parse_acoustid(json.load(resp))


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

def run(ctx):
    path = ctx.ask_file()
    if path is None:
        return
    info = media.probe(path)
    audio = media.streams(info, "audio")
    if not audio:
        ctx.print(ctx.t("music_check.no_audio"))
        return
    a = audio[0]
    ctx.print(ctx.t("music_check.track", codec=a.get("codec_name", "?"),
                    rate=a.get("sample_rate", "?"), channels=a.get("channels", "?"),
                    seconds=ctx.translator.format_number(round(media.duration(info), 1))))
    if len(audio) > 1:
        ctx.print(ctx.t("music_check.multiple_tracks", count=len(audio)))

    ctx.print(ctx.t("music_check.measuring"))
    loud = measure(path)
    notes = verdict(loud)
    if notes != ["music_check.silent"]:
        ctx.print(ctx.t("music_check.loudness", lufs=f"{loud.integrated:.1f}",
                        peak=f"{loud.true_peak:.1f}", target=f"{TARGET_LUFS:.0f}"))
    for key in notes:
        ctx.print("  " + ctx.t(key))

    fixable = any(k in notes for k in ("music_check.too_quiet", "music_check.too_loud",
                                        "music_check.peak_high"))
    if fixable and ctx.confirm(ctx.t("music_check.ask_normalize")):
        out = normalize(path, loud, bool(media.streams(info, "video")))
        ctx.print(ctx.t("music_check.normalized", path=str(out)))

    key = acoustid_key(ctx)
    if not key:
        ctx.print(ctx.t("music_check.identify_hint"))
        return
    if notes == ["music_check.silent"] or not ctx.confirm(ctx.t("music_check.ask_identify")):
        return
    try:
        matches = identify(path, key)
    except (OSError, RuntimeError, ValueError) as exc:
        ctx.print(ctx.t("music_check.identify_failed", error=str(exc)))
        return
    if not matches:
        ctx.print(ctx.t("music_check.no_match"))
        return
    ctx.print(ctx.t("music_check.matches"))
    for score, title, artists in matches[:5]:
        ctx.print(f"  {round(score * 100)}%  {title} – {artists}")
    ctx.print(ctx.t("music_check.copyright_note"))
