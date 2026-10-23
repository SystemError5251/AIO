"""Thin helpers around ffmpeg/ffprobe, shared by the video plugins.

On Termux install them with `pkg install ffmpeg`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".3gp", ".avi"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}


# Termux package that provides a program, where the names differ.
PACKAGES = {"ffprobe": "ffmpeg", "fpcalc": "chromaprint", "termux-share": "termux-api"}


class MissingTool(RuntimeError):
    """A required command line program is not installed."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name
        self.package = PACKAGES.get(name, name)


def require(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MissingTool(name)
    return path


def has(name: str) -> bool:
    return shutil.which(name) is not None


def probe(path: Path) -> dict[str, Any]:
    """ffprobe as JSON: {"format": {...}, "streams": [...]}."""
    result = subprocess.run(
        [require("ffprobe"), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"ffprobe failed for {path}")
    return json.loads(result.stdout or "{}")


def ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg quietly; raises RuntimeError with ffmpeg's last lines on failure."""
    result = subprocess.run(
        [require("ffmpeg"), "-hide_banner", "-nostdin", *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise RuntimeError(tail or "ffmpeg failed")
    return result


def streams(info: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == kind]


def duration(info: dict[str, Any]) -> float:
    try:
        return float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        return 0.0


def display_size(stream: dict[str, Any]) -> tuple[int, int]:
    """Width/height as shown on screen, honouring 90/270 degree rotation."""
    w, h = int(stream.get("width", 0)), int(stream.get("height", 0))
    rotation = 0
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = int(float(side["rotation"]))
    if not rotation:
        rotation = int(float(stream.get("tags", {}).get("rotate", 0) or 0))
    return (h, w) if abs(rotation) % 180 == 90 else (w, h)


def output_path(src: Path, suffix: str, ext: str | None = None) -> Path:
    """`clip.mp4` -> `clip.<suffix>.mp4`, never overwriting an existing file."""
    ext = ext or src.suffix
    candidate = src.with_name(f"{src.stem}.{suffix}{ext}")
    n = 2
    while candidate.exists():
        candidate = src.with_name(f"{src.stem}.{suffix}-{n}{ext}")
        n += 1
    return candidate
