"""Upload helper for Reels / Shorts / TikTok.

Checks a clip against each platform's limits (platforms.json), converts it to
1080x1920 H.264/AAC if needed (metadata removed on the way), and hands the
result to the Android share menu via `termux-share` so the user picks the app.
No accounts or API keys are needed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aio.core import media

PLATFORMS_FILE = Path(__file__).with_name("platforms.json")
TARGET_W, TARGET_H = 1080, 1920
VERTICAL = TARGET_W / TARGET_H
GOOD_VIDEO_CODECS = {"h264", "hevc"}
GOOD_AUDIO_CODECS = {"aac"}
MAX_FPS = 60


def load_platforms(path: Path = PLATFORMS_FILE) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


@dataclass
class Check:
    issues: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # (key, kwargs)
    notes: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    needs_convert: bool = False
    trim_to: float | None = None

    @property
    def ok(self) -> bool:
        return not self.issues


def _fps(stream: dict[str, Any]) -> float:
    try:
        num, den = stream.get("avg_frame_rate", "0/1").split("/")
        return float(num) / float(den) if float(den) else 0.0
    except ValueError:
        return 0.0


def check(info: dict[str, Any], platform: dict[str, Any]) -> Check:
    result = Check()
    video = media.streams(info, "video")
    if not video:
        result.issues.append(("video_upload.no_video", {}))
        return result
    v = video[0]
    w, h = media.display_size(v)
    ratio = w / h if h else 0

    if abs(ratio - VERTICAL) > 0.02:
        square_ok = platform.get("allow_square") and abs(ratio - 1) <= 0.02
        if ratio > 1 or not square_ok:
            result.issues.append(("video_upload.not_vertical", {"w": w, "h": h}))
            result.needs_convert = True
    if min(w, h) < 720:
        result.notes.append(("video_upload.low_resolution", {"w": w, "h": h}))
    if v.get("codec_name") not in GOOD_VIDEO_CODECS:
        result.issues.append(("video_upload.bad_video_codec", {"codec": v.get("codec_name", "?")}))
        result.needs_convert = True
    fps = _fps(v)
    if fps > MAX_FPS + 0.5:
        result.issues.append(("video_upload.high_fps", {"fps": round(fps)}))
        result.needs_convert = True

    audio = media.streams(info, "audio")
    if not audio:
        result.notes.append(("video_upload.no_audio", {}))
    elif audio[0].get("codec_name") not in GOOD_AUDIO_CODECS:
        result.issues.append(("video_upload.bad_audio_codec", {"codec": audio[0].get("codec_name", "?")}))
        result.needs_convert = True

    seconds = media.duration(info)
    limit = platform.get("max_seconds")
    if limit and seconds > limit:
        result.issues.append(("video_upload.too_long", {"seconds": round(seconds), "limit": limit}))
        result.needs_convert = True
        result.trim_to = float(limit)
    return result


def convert_args(src: Path, dst: Path, fps: float, trim_to: float | None) -> list[str]:
    vf = (f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,"
          f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    if fps > MAX_FPS + 0.5:
        vf += f",fps={MAX_FPS}"
    args = ["-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart"]
    if trim_to:
        args += ["-t", str(trim_to)]
    return [*args, str(dst)]


def convert(src: Path, info: dict[str, Any], result: Check, platform_id: str) -> Path:
    dst = media.output_path(src, platform_id, ".mp4")
    media.ffmpeg(convert_args(src, dst, _fps(media.streams(info, "video")[0]), result.trim_to))
    return dst


def share(path: Path) -> None:
    subprocess.run([media.require("termux-share"), "-a", "send", "-c", "video/mp4", str(path)],
                   check=True)


def _choose_platform(ctx, platforms: dict[str, dict[str, Any]]) -> str | None:
    ids = list(platforms)
    ctx.print(ctx.t("video_upload.choose_platform"))
    for i, pid in enumerate(ids, 1):
        p = platforms[pid]
        ctx.print(f"   {i}) {p['label']}  " + ctx.t("video_upload.max_length", seconds=p["max_seconds"]))
    while True:
        answer = ctx.ask(ctx.t("menu.prompt") + " ")
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(ids):
            return ids[int(answer) - 1]
        ctx.print(ctx.t("menu.invalid"))


def run(ctx):
    path = ctx.ask_file()
    if path is None:
        return
    platforms = load_platforms()
    pid = _choose_platform(ctx, platforms)
    if pid is None:
        return
    info = media.probe(path)
    result = check(info, platforms[pid])
    ctx.print()
    ctx.print(ctx.t("video_upload.report", platform=platforms[pid]["label"]))
    for key, kwargs in result.issues:
        ctx.print("  ✗ " + ctx.t(key, **kwargs))
    for key, kwargs in result.notes:
        ctx.print("  ! " + ctx.t(key, **kwargs))
    if result.ok:
        ctx.print("  ✓ " + ctx.t("video_upload.all_good"))
    if not media.streams(info, "video"):
        return

    final = path
    if result.needs_convert:
        if result.trim_to:
            ctx.print(ctx.t("video_upload.will_trim", limit=round(result.trim_to)))
        if not ctx.confirm(ctx.t("video_upload.ask_convert")):
            return
        ctx.print(ctx.t("video_upload.converting"))
        final = convert(path, info, result, pid)
        ctx.print(ctx.t("video_upload.converted", path=str(final)))

    if not media.has("termux-share"):
        ctx.print(ctx.t("video_upload.share_missing", path=str(final)))
        return
    if ctx.confirm(ctx.t("video_upload.ask_share", platform=platforms[pid]["label"])):
        share(final)
