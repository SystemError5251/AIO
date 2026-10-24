"""Loudnorm: bring many clips or audio files to the same loudness in one go.

Targets: -14 LUFS (Reels/Shorts/TikTok/Spotify), -16 LUFS (podcasts) or
-23 LUFS (EBU R128, broadcast). Two passes per file (measure, then correct
linearly); video is copied unchanged. Files already on target are skipped.
"""

from __future__ import annotations

from pathlib import Path

from aio.core import audio, media

TARGETS = [(-14.0, "loudnorm.target_social"), (-16.0, "loudnorm.target_podcast"),
           (-23.0, "loudnorm.target_broadcast")]
TOLERANCE_LU = 1.0


def collect(path: Path) -> list[Path]:
    exts = media.VIDEO_EXTS | media.AUDIO_EXTS
    files = sorted(path.iterdir()) if path.is_dir() else [path]
    return [f for f in files if f.is_file() and f.suffix.lower() in exts and ".lufs" not in f.name]


def on_target(loud: audio.Loudness, target: float) -> bool:
    return abs(loud.integrated - target) <= TOLERANCE_LU and loud.true_peak <= audio.MAX_TRUE_PEAK


def suffix(target: float) -> str:
    return f"lufs{abs(int(target))}"


def run(ctx):
    path = ctx.ask_file(ctx.t("loudnorm.ask_path"), allow_dir=True)
    if path is None:
        return
    files = collect(path)
    if not files:
        ctx.print(ctx.t("loudnorm.nothing_found"))
        return
    ctx.print(ctx.t("loudnorm.choose_target"))
    for i, (lufs, key) in enumerate(TARGETS, 1):
        ctx.print(f"   {i}) {lufs:g} LUFS – {ctx.t(key)}")
    answer = ctx.ask(ctx.t("menu.prompt") + " ")
    if not answer or not answer.isdigit() or not 1 <= int(answer) <= len(TARGETS):
        return
    target = TARGETS[int(answer) - 1][0]

    done = 0
    for f in files:
        ctx.print()
        ctx.print(f"[{f.name}]")
        try:
            info = media.probe(f)
            if not media.streams(info, "audio"):
                ctx.print("  " + ctx.t("loudnorm.no_audio"))
                continue
            loud = audio.measure(f, target)
            if loud.silent:
                ctx.print("  " + ctx.t("loudnorm.silent"))
                continue
            ctx.print("  " + ctx.t("loudnorm.measured", lufs=f"{loud.integrated:.1f}",
                                   peak=f"{loud.true_peak:.1f}"))
            if on_target(loud, target):
                ctx.print("  " + ctx.t("loudnorm.already_ok"))
                continue
            out = audio.normalize(f, loud, audio.has_real_video(info), target,
                                  suffix=suffix(target))
        except RuntimeError as exc:
            ctx.print("  " + ctx.t("loudnorm.failed", error=str(exc)))
            continue
        done += 1
        ctx.print("  " + ctx.t("loudnorm.saved", path=out.name))
    ctx.print()
    ctx.print(ctx.t("loudnorm.summary", count=done, total=len(files)))
