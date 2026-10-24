"""Zuschneiden: crop a video to 9:16, 1:1, 4:5 or 16:9 and/or cut start and end.

The crop keeps the centre, or the left/top or right/bottom part. Sizes are
taken as shown on screen (rotation from the phone is honoured).
"""

from __future__ import annotations

import re
from pathlib import Path

from aio.core import media

RATIOS = [(9, 16), (1, 1), (4, 5), (16, 9)]
ANCHORS = ["center", "start", "end"]


def crop_box(w: int, h: int, rw: int, rh: int, anchor: str = "center") -> tuple[int, int, int, int]:
    """Largest (width, height, x, y) with ratio rw:rh inside w×h; even numbers for H.264."""
    if w * rh > h * rw:            # too wide: cut left/right
        ch = h - h % 2
        cw = min(w, ch * rw // rh)
    else:                          # too tall: cut top/bottom
        cw = w - w % 2
        ch = min(h, cw * rh // rw)
    cw, ch = cw - cw % 2, ch - ch % 2
    free_x, free_y = w - cw, h - ch
    pos = {"center": 0.5, "start": 0.0, "end": 1.0}[anchor]
    x, y = int(free_x * pos), int(free_y * pos)
    return cw, ch, x - x % 2, y - y % 2


def parse_time(text: str) -> float | None:
    """"75", "1:15", "0:01:15" or "1:15.5" -> seconds; None if not a time."""
    text = text.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}(\.\d+)?", text):
        return None
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def crop_args(src: Path, out: Path, box: tuple[int, int, int, int] | None,
              start: float | None, end: float | None) -> list[str]:
    args = ["-y"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if end is not None:
        args += ["-t", f"{end - (start or 0):.3f}"]
    args += ["-map", "0:v:0", "-map", "0:a?"]
    if box:
        cw, ch, x, y = box
        args += ["-vf", f"crop={cw}:{ch}:{x}:{y},setsar=1"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    return args


def _ask_time(ctx, key: str, limit: float) -> float | None | bool:
    """None = not set, False = cancelled."""
    while True:
        answer = ctx.ask(ctx.t(key) + " ")
        if answer is None:
            return False
        if not answer:
            return None
        value = parse_time(answer)
        if value is not None and 0 <= value <= limit:
            return value
        ctx.print(ctx.t("video_crop.bad_time", limit=f"{limit:.1f}"))


def run(ctx):
    src = ctx.ask_file()
    if src is None:
        return
    info = media.probe(src)
    video = media.streams(info, "video")
    if not video:
        ctx.print(ctx.t("video_crop.no_video"))
        return
    w, h = media.display_size(video[0])
    length = media.duration(info)
    ctx.print(ctx.t("video_crop.info", w=w, h=h, seconds=f"{length:.1f}"))

    ctx.print(ctx.t("video_crop.choose_ratio"))
    ctx.print("   0) " + ctx.t("video_crop.keep_ratio"))
    for i, (rw, rh) in enumerate(RATIOS, 1):
        ctx.print(f"   {i}) {rw}:{rh}")
    answer = ctx.ask(ctx.t("menu.prompt") + " ")
    if answer is None or not answer.isdigit() or int(answer) > len(RATIOS):
        return
    box = None
    if int(answer):
        rw, rh = RATIOS[int(answer) - 1]
        anchor = "center"
        if w * rh != h * rw:
            wide = w * rh > h * rw
            ctx.print(ctx.t("video_crop.choose_anchor"))
            ctx.print("   1) " + ctx.t("video_crop.anchor_center"))
            ctx.print("   2) " + ctx.t("video_crop.anchor_left" if wide else "video_crop.anchor_top"))
            ctx.print("   3) " + ctx.t("video_crop.anchor_right" if wide else "video_crop.anchor_bottom"))
            pick = ctx.ask(ctx.t("menu.prompt") + " ")
            if pick is None:
                return
            anchor = ANCHORS[int(pick) - 1] if pick in ("1", "2", "3") else "center"
        box = crop_box(w, h, rw, rh, anchor)
        if box[:2] == (w, h):
            box = None

    start = _ask_time(ctx, "video_crop.ask_start", length)
    if start is False:
        return
    end = _ask_time(ctx, "video_crop.ask_end", length)
    if end is False:
        return
    if end is not None and end <= (start or 0):
        ctx.print(ctx.t("video_crop.end_before_start"))
        return
    if box is None and not start and end is None:
        ctx.print(ctx.t("video_crop.nothing_to_do"))
        return

    ctx.print(ctx.t("video_crop.working"))
    out = media.output_path(src, "crop", ".mp4")
    media.ffmpeg(crop_args(src, out, box, start, end))
    ctx.print(ctx.t("video_crop.saved", path=str(out)))
