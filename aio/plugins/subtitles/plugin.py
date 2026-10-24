"""Untertitel: burn an .srt/.ass/.vtt file into a video, or add it as a switchable track.

Burned-in subtitles are always visible (what Reels/TikTok need); a subtitle
track is quick (no re-encode) and can be switched off in players. The file is
checked first: number of cues, broken timestamps, cues after the video ends.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import media

SUB_EXTS = (".srt", ".vtt", ".ass", ".ssa")
TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
TIME_SHORT = re.compile(r"(\d{2}):(\d{2})[.](\d{3})\s*-->\s*(\d{2}):(\d{2})[.](\d{3})")  # vtt mm:ss.mmm
FONT_SIZE = 16


@dataclass
class Cue:
    start: float
    end: float
    text: str


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse_cues(text: str) -> list[Cue]:
    """SRT and WebVTT cues; other lines (numbers, WEBVTT header, notes) are ignored."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        for i, line in enumerate(lines):
            m = TIME.search(line)
            if m:
                start, end = _seconds(*m.groups()[:4]), _seconds(*m.groups()[4:])
            else:
                m = TIME_SHORT.search(line)
                if not m:
                    continue
                g = m.groups()
                start, end = _seconds("0", *g[:3]), _seconds("0", *g[3:])
            cues.append(Cue(start, end, "\n".join(lines[i + 1:]).strip()))
            break
    return cues


def problems(cues: list[Cue], video_seconds: float) -> list[tuple[str, dict[str, Any]]]:
    if not cues:
        return [("subtitles.no_cues", {})]
    found = []
    broken = sum(1 for c in cues if c.end <= c.start)
    if broken:
        found.append(("subtitles.broken_times", {"count": broken}))
    late = sum(1 for c in cues if video_seconds and c.start >= video_seconds)
    if late:
        found.append(("subtitles.after_end", {"count": late}))
    return found


def find_subtitle(video: Path) -> Path | None:
    """clip.srt, or a language-tagged clip.de.srt next to the video."""
    for ext in SUB_EXTS:
        if (candidate := video.with_suffix(ext)).is_file():
            return candidate
    for ext in SUB_EXTS:
        tagged = sorted(video.parent.glob(f"{video.stem}.*{ext}"))
        if tagged:
            return tagged[0]
    return None


def _clean_copy(sub: Path, folder: Path) -> Path:
    """UTF-8 copy with a plain name, so ffmpeg's filter syntax needs no escaping."""
    target = folder / f"subs{sub.suffix.lower()}"
    target.write_text(read_text(sub), encoding="utf-8")
    return target


def burn_args(video: Path, sub: Path, out: Path) -> list[str]:
    style = f"FontSize={FONT_SIZE},Outline=2,Shadow=0,MarginV=40"
    vf = f"subtitles={sub.as_posix()}"
    if sub.suffix.lower() in (".srt", ".vtt"):
        vf += f":force_style='{style}'"
    return ["-y", "-i", str(video), "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", str(out)]


def track_args(video: Path, sub: Path, out: Path) -> list[str]:
    codec = "mov_text" if out.suffix == ".mp4" else "srt"
    if sub.suffix.lower() in (".ass", ".ssa") and out.suffix == ".mkv":
        codec = "ass"
    return ["-y", "-i", str(video), "-i", str(sub), "-map", "0:v", "-map", "0:a?", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", codec, str(out)]


def apply(video: Path, sub: Path, burn: bool) -> Path:
    ext = ".mkv" if video.suffix.lower() in (".mkv", ".webm") and not burn else ".mp4"
    out = media.output_path(video, "subtitled" if burn else "subs", ext)
    with tempfile.TemporaryDirectory() as tmp:
        clean = _clean_copy(sub, Path(tmp))
        media.ffmpeg((burn_args if burn else track_args)(video, clean, out))
    return out


def run(ctx):
    video = ctx.ask_file()
    if video is None:
        return
    info = media.probe(video)
    if not media.streams(info, "video"):
        ctx.print(ctx.t("subtitles.no_video"))
        return
    sub = find_subtitle(video)
    if sub is not None:
        ctx.print(ctx.t("subtitles.found", path=str(sub)))
        if not ctx.confirm(ctx.t("subtitles.use_found")):
            sub = None
    if sub is None:
        sub = ctx.ask_file(ctx.t("subtitles.ask_file"))
        if sub is None:
            return
    if sub.suffix.lower() not in SUB_EXTS:
        ctx.print(ctx.t("subtitles.unsupported", ext=sub.suffix or "?"))
        return

    if sub.suffix.lower() in (".srt", ".vtt"):
        cues = parse_cues(read_text(sub))
        if cues:
            last = max(c.end for c in cues)
            ctx.print(ctx.t("subtitles.summary", count=len(cues),
                            last=f"{int(last // 60)}:{int(last % 60):02d}"))
        issues = problems(cues, media.duration(info))
        for key, kwargs in issues:
            ctx.print("  ! " + ctx.t(key, **kwargs))
        if not cues:
            return

    ctx.print(ctx.t("subtitles.choose_mode"))
    ctx.print("   1) " + ctx.t("subtitles.mode_burn"))
    ctx.print("   2) " + ctx.t("subtitles.mode_track"))
    answer = ctx.ask(ctx.t("menu.prompt") + " ")
    if answer not in ("1", "2"):
        return
    burn = answer == "1"
    ctx.print(ctx.t("subtitles.working_burn" if burn else "subtitles.working_track"))
    out = apply(video, sub, burn)
    ctx.print(ctx.t("subtitles.saved", path=str(out)))
