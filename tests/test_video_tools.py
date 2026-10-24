import subprocess

import pytest

from aio.core import audio, config, media, registry
from aio.core.main import main

needs_ffmpeg = pytest.mark.skipif(not (media.has("ffmpeg") and media.has("ffprobe")),
                                  reason="ffmpeg not installed")

SRT = """1
00:00:00,100 --> 00:00:00,800
Hallo Welt

2
00:00:01,000 --> 00:00:00,500
kaputt

3
00:00:09,000 --> 00:00:10,000
zu spät
"""

VTT = """WEBVTT

00:00.100 --> 00:00.900
eins

00:00:01.000 --> 00:00:01.500
zwei
"""


def plugin(pid):
    return {p.id: p for p in registry.discover()}[pid].load()


def make_clip(path, size="1280x720", seconds=2, tone=True, volume=1.0):
    args = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25"]
    if tone:
        args += ["-f", "lavfi", "-i", "sine=frequency=440"]
        args += ["-af", f"volume={volume}"]
    subprocess.run([*args, "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


# -- subtitles -------------------------------------------------------------- #

def test_parse_srt_and_problems():
    st = plugin("subtitles")
    cues = st.parse_cues(SRT)
    assert [c.text for c in cues] == ["Hallo Welt", "kaputt", "zu spät"]
    assert cues[0].start == 0.1 and cues[0].end == 0.8
    assert st.problems(cues, 5.0) == [("subtitles.broken_times", {"count": 1}),
                                      ("subtitles.after_end", {"count": 1})]
    assert st.problems([], 5.0) == [("subtitles.no_cues", {})]


def test_parse_vtt_short_and_long_times():
    cues = plugin("subtitles").parse_cues(VTT)
    assert [(c.start, c.end, c.text) for c in cues] == [(0.1, 0.9, "eins"), (1.0, 1.5, "zwei")]


def test_read_text_falls_back_to_cp1252(tmp_path):
    f = tmp_path / "x.srt"
    f.write_bytes("Größe".encode("cp1252"))
    assert plugin("subtitles").read_text(f) == "Größe"


def test_find_subtitle_prefers_same_name(tmp_path):
    st = plugin("subtitles")
    video = tmp_path / "clip.mp4"
    video.touch()
    assert st.find_subtitle(video) is None
    (tmp_path / "clip.de.srt").touch()
    assert st.find_subtitle(video).name == "clip.de.srt"
    (tmp_path / "clip.srt").touch()
    assert st.find_subtitle(video).name == "clip.srt"


@needs_ffmpeg
@pytest.mark.parametrize("burn,suffix,codec", [(True, "subtitled", None), (False, "subs", "mov_text")])
def test_subtitles_end_to_end(tmp_path, term, burn, suffix, codec):
    video = make_clip(tmp_path / "clip mit leerzeichen.mp4")
    (tmp_path / "clip mit leerzeichen.srt").write_text(SRT, encoding="utf-8")
    config.set_value("language", "en")
    index = [p.id for p in registry.discover()].index("subtitles") + 1
    t = term([str(index), "", str(video), "y", "1" if burn else "2", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "3 subtitles, the last one ends at 0:10." in t.text
    assert "1 subtitle starts after the video ends." in t.text
    out = tmp_path / f"clip mit leerzeichen.{suffix}.mp4"
    assert out.is_file(), t.text
    subs = media.streams(media.probe(out), "subtitle")
    assert (subs[0]["codec_name"] if subs else None) == codec


# -- loudnorm --------------------------------------------------------------- #

def test_loudnorm_helpers(tmp_path):
    ln = plugin("loudnorm")
    for name in ("a.mp4", "b.mp3", "notes.txt", "a.lufs14.mp4"):
        (tmp_path / name).touch()
    assert [f.name for f in ln.collect(tmp_path)] == ["a.mp4", "b.mp3"]
    assert ln.on_target(audio.Loudness(-14.4, -1.5, 5, -24), -14)
    assert not ln.on_target(audio.Loudness(-14.4, -0.5, 5, -24), -14)
    assert not ln.on_target(audio.Loudness(-20, -3, 5, -30), -14)
    assert ln.suffix(-23.0) == "lufs23"


def test_has_real_video_ignores_cover_art():
    cover = {"streams": [{"codec_type": "audio"},
                         {"codec_type": "video", "disposition": {"attached_pic": 1}}]}
    assert not audio.has_real_video(cover)
    assert audio.has_real_video({"streams": [{"codec_type": "video", "disposition": {}}]})


@needs_ffmpeg
def test_loudnorm_folder_end_to_end(tmp_path, term):
    make_clip(tmp_path / "quiet.mp4", volume=0.05)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300",
                    "-t", "2", "-af", "volume=0.05", str(tmp_path / "voice.m4a")], check=True)
    make_clip(tmp_path / "silent.mp4", tone=False)
    config.set_value("language", "en")
    index = [p.id for p in registry.discover()].index("loudnorm") + 1
    t = term([str(index), "", str(tmp_path), "2", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "No audio track, skipped." in t.text
    assert "Done: 2 of 3 files adjusted." in t.text
    out = tmp_path / "quiet.lufs16.mp4"
    assert out.is_file() and (tmp_path / "voice.lufs16.m4a").is_file()
    assert abs(audio.measure(out, -16).integrated + 16) < 1.5
    assert media.streams(media.probe(out), "video")


# -- crop ------------------------------------------------------------------- #

@pytest.mark.parametrize("w,h,ratio,anchor,box", [
    (1920, 1080, (9, 16), "center", (606, 1080, 656, 0)),
    (1920, 1080, (9, 16), "start", (606, 1080, 0, 0)),
    (1920, 1080, (9, 16), "end", (606, 1080, 1314, 0)),
    (1080, 1920, (1, 1), "center", (1080, 1080, 0, 420)),
    (1080, 1920, (4, 5), "end", (1080, 1350, 0, 570)),
    (1080, 1920, (9, 16), "center", (1080, 1920, 0, 0)),
    (721, 1281, (1, 1), "center", (720, 720, 0, 280)),
])
def test_crop_box(w, h, ratio, anchor, box):
    result = plugin("video_crop").crop_box(w, h, *ratio, anchor)
    assert result == box
    cw, ch, x, y = result
    assert cw % 2 == ch % 2 == x % 2 == y % 2 == 0 and x + cw <= w and y + ch <= h


@pytest.mark.parametrize("text,seconds", [("75", 75), ("1:15", 75), ("0:01:15", 75),
                                          ("1:15,5", 75.5), ("abc", None), ("1:2:3:4", None)])
def test_parse_time(text, seconds):
    assert plugin("video_crop").parse_time(text) == seconds


@needs_ffmpeg
def test_crop_end_to_end(tmp_path, term):
    video = make_clip(tmp_path / "wide.mp4", seconds=3)
    config.set_value("language", "en")
    index = [p.id for p in registry.discover()].index("video_crop") + 1
    t = term([str(index), "", str(video), "1", "2", "0:01", "99", "2.5", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Invalid time." in t.text
    info = media.probe(tmp_path / "wide.crop.mp4")
    assert media.display_size(media.streams(info, "video")[0]) == (404, 720)
    assert abs(media.duration(info) - 1.5) < 0.2
