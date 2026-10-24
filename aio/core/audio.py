"""Loudness measurement and two-pass loudnorm correction (shared by audio tools)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import media

SOCIAL_LUFS = -14.0  # Reels/Shorts/TikTok/Spotify normalise to this
MAX_TRUE_PEAK = -1.0


@dataclass
class Loudness:
    integrated: float  # LUFS, -inf for silence
    true_peak: float   # dBTP
    lra: float         # LU
    threshold: float

    @property
    def silent(self) -> bool:
        return self.integrated == float("-inf") or self.integrated < -70


def has_real_video(info: dict[str, Any]) -> bool:
    """A video stream that is not just cover art (attached picture in an MP3/M4A)."""
    return any(not s.get("disposition", {}).get("attached_pic")
               for s in media.streams(info, "video"))


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


def measure(path: Path, target: float = SOCIAL_LUFS, true_peak: float = MAX_TRUE_PEAK) -> Loudness:
    result = media.ffmpeg(["-i", str(path), "-vn", "-af",
                           f"loudnorm=I={target}:TP={true_peak}:LRA=11:print_format=json",
                           "-f", "null", "-"])
    return parse_loudnorm(result.stderr)


def normalize(path: Path, loud: Loudness, has_video: bool, target: float = SOCIAL_LUFS,
              true_peak: float = MAX_TRUE_PEAK, suffix: str = "loudnorm") -> Path:
    """Second loudnorm pass with the measured values (accurate, linear). Video is copied."""
    out = media.output_path(path, suffix, ".mp4" if has_video else ".m4a")
    filt = (f"loudnorm=I={target}:TP={true_peak}:LRA=11:"
            f"measured_I={loud.integrated}:measured_TP={loud.true_peak}:"
            f"measured_LRA={loud.lra}:measured_thresh={loud.threshold}:linear=true")
    args = ["-y", "-i", str(path)]
    if has_video:
        args += ["-map", "0:v:0", "-c:v", "copy", "-movflags", "+faststart"]
    args += ["-map", "0:a:0", "-af", filt, "-ar", "48000", "-c:a", "aac", "-b:a", "192k"]
    media.ffmpeg([*args, str(out)])
    return out
