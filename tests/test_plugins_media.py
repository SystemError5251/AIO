import shutil
import struct
import subprocess
import zlib

import pytest

from aio.core import config, media, registry
from aio.core.main import main

needs_ffmpeg = pytest.mark.skipif(not (media.has("ffmpeg") and media.has("ffprobe")),
                                  reason="ffmpeg not installed")


def plugin(pid):
    return {p.id: p for p in registry.discover()}[pid].load()


def make_clip(path, size="720x1280", seconds=1, extra=()):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(seconds),
                    *extra, str(path)], check=True)
    return path


# --------------------------------------------------------------------------- #
# Privacy stripper
# --------------------------------------------------------------------------- #

def _exif_segment(orientation=6, gps=True):
    entries = [struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0)]
    if gps:
        entries.append(struct.pack(">HHII", 0x8825, 4, 1, 0))
    tiff = (b"MM\x00\x2a" + struct.pack(">I", 8) + struct.pack(">H", len(entries))
            + b"".join(entries) + struct.pack(">I", 0))
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _segment(marker, payload):
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def _fake_jpeg():
    jfif = _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    xmp = _segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>")
    com = _segment(0xFE, b"shot by JR")
    icc = _segment(0xE2, b"ICC_PROFILE\x00data")
    scan = b"\xff\xda" + struct.pack(">H", 2) + b"IMAGEDATA\xff\xd9"
    return b"\xff\xd8" + jfif + _exif_segment() + xmp + com + icc + scan


def test_strip_jpeg_removes_metadata_keeps_orientation_and_pixels():
    ps = plugin("privacy_strip")
    cleaned, found = ps.strip_jpeg(_fake_jpeg())
    assert set(found) == {"EXIF", "GPS", "XMP", "COMMENT"}
    assert b"shot by JR" not in cleaned and b"xmpmeta" not in cleaned
    assert b"ICC_PROFILE" in cleaned and cleaned.endswith(b"IMAGEDATA\xff\xd9")
    # the only EXIF left carries the orientation, no GPS pointer
    _, again = ps.strip_jpeg(cleaned)
    assert again == ["EXIF"]
    start = cleaned.index(b"Exif\x00\x00")
    assert ps._exif_info(cleaned[start:start + 40]) == (6, False)


def test_strip_jpeg_without_rotation_adds_nothing():
    ps = plugin("privacy_strip")
    data = _fake_jpeg().replace(_exif_segment(), _exif_segment(orientation=1, gps=False))
    cleaned, _ = ps.strip_jpeg(data)
    assert b"Exif" not in cleaned


def _png_chunk(ctype, data):
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data))


def test_strip_png():
    ps = plugin("privacy_strip")
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    png = (ps.PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr)
           + _png_chunk(b"tEXt", b"Author\x00JR") + _png_chunk(b"eXIf", b"MM")
           + _png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
           + _png_chunk(b"IEND", b""))
    cleaned, found = ps.strip_png(png)
    assert found == ["tEXt", "eXIf"]
    assert b"Author" not in cleaned and b"IDAT" in cleaned and cleaned.endswith(_png_chunk(b"IEND", b""))


def test_clean_file_never_overwrites(tmp_path):
    ps = plugin("privacy_strip")
    src = tmp_path / "photo.jpg"
    src.write_bytes(_fake_jpeg())
    first, second = ps.clean_file(src), ps.clean_file(src)
    assert first.output.name == "photo.clean.jpg"
    assert second.output.name == "photo.clean-2.jpg"
    assert src.read_bytes() == _fake_jpeg()


def test_collect_folder_skips_clean_copies(tmp_path):
    ps = plugin("privacy_strip")
    for name in ("a.jpg", "b.mp4", "a.clean.jpg", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in ps.collect(tmp_path)] == ["a.jpg", "b.mp4"]


@needs_ffmpeg
def test_strip_video_removes_location_and_time(tmp_path):
    ps = plugin("privacy_strip")
    src = make_clip(tmp_path / "clip.mp4", extra=[
        "-metadata", "location=+52.5200+013.4050/", 
        "-metadata", "creation_time=2026-01-01T10:00:00Z"])
    result = ps.clean_file(src)
    assert "location" in result.found and "creation_time" in result.found
    assert result.error is None and result.remaining == []
    assert media.streams(media.probe(result.output), "video")


def test_privacy_strip_through_menu(tmp_path, term):
    config.set_value("language", "de")
    src = tmp_path / "photo.jpg"
    src.write_bytes(_fake_jpeg())
    index = [p.id for p in registry.discover()].index("privacy_strip") + 1
    t = term([str(index), "", str(src), "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "4 Einträge entfernt: EXIF, GPS, XMP, COMMENT" in t.text
    assert "Fertig: 1 von 1 Datei bereinigt." in t.text


# --------------------------------------------------------------------------- #
# Music check
# --------------------------------------------------------------------------- #

LOUDNORM_LOG = """[Parsed_loudnorm_0 @ 0x1]
{
	"input_i" : "-21.76",
	"input_tp" : "-17.69",
	"input_lra" : "0.00",
	"input_thresh" : "-31.76",
	"output_i" : "-14.0"
}
"""


def test_parse_loudnorm_and_verdict():
    mc = plugin("music_check")
    loud = mc.parse_loudnorm(LOUDNORM_LOG)
    assert loud.integrated == -21.76 and loud.true_peak == -17.69
    assert mc.verdict(loud) == ["music_check.too_quiet"]
    assert mc.verdict(mc.Loudness(-14.5, -0.2, 3, -24)) == ["music_check.loudness_ok", "music_check.peak_high"]
    assert mc.verdict(mc.Loudness(-9, -2, 3, -19)) == ["music_check.too_loud"]
    assert mc.verdict(mc.Loudness(float("-inf"), float("-inf"), 0, -70)) == ["music_check.silent"]


def test_parse_loudnorm_without_json_raises():
    with pytest.raises(RuntimeError):
        plugin("music_check").parse_loudnorm("nothing here")


def test_parse_acoustid():
    mc = plugin("music_check")
    data = {"status": "ok", "results": [
        {"score": 0.3, "recordings": [{"title": "Low", "artists": [{"name": "X"}]}]},
        {"score": 0.93, "recordings": [
            {"title": "Song", "artists": [{"name": "A"}, {"name": "B"}]},
            {"title": "Song", "artists": [{"name": "A"}, {"name": "B"}]},
            {"id": "no-title"}]},
    ]}
    assert mc.parse_acoustid(data) == [(0.93, "Song", "A, B")]
    with pytest.raises(RuntimeError):
        mc.parse_acoustid({"status": "error", "error": {"message": "invalid API key"}})


@needs_ffmpeg
def test_measure_and_normalize(tmp_path):
    mc = plugin("music_check")
    src = make_clip(tmp_path / "clip.mp4", seconds=3)
    loud = mc.measure(src)
    assert "music_check.too_quiet" in mc.verdict(loud)
    fixed = mc.measure(mc.normalize(src, loud, has_video=True))
    assert abs(fixed.integrated - mc.TARGET_LUFS) < 1.0


# --------------------------------------------------------------------------- #
# Upload helper
# --------------------------------------------------------------------------- #

def _info(w=1080, h=1920, vcodec="h264", acodec="aac", fps="30/1", seconds=20.0, rotation=None):
    v = {"codec_type": "video", "codec_name": vcodec, "width": w, "height": h, "avg_frame_rate": fps}
    if rotation is not None:
        v["side_data_list"] = [{"rotation": rotation}]
    streams = [v] + ([{"codec_type": "audio", "codec_name": acodec}] if acodec else [])
    return {"format": {"duration": str(seconds)}, "streams": streams}


def test_upload_check_rules():
    vu = plugin("video_upload")
    pl = vu.load_platforms()
    assert set(pl) == {"youtube_shorts", "instagram_reels", "tiktok"}
    assert vu.check(_info(), pl["tiktok"]).ok

    wide = vu.check(_info(1920, 1080), pl["tiktok"])
    assert ("video_upload.not_vertical", {"w": 1920, "h": 1080}) in wide.issues and wide.needs_convert

    # phone video stored landscape with a 90° rotation flag is really vertical
    assert vu.check(_info(1920, 1080, rotation=-90), pl["tiktok"]).ok

    assert vu.check(_info(1080, 1080), pl["youtube_shorts"]).ok
    assert not vu.check(_info(1080, 1080), pl["instagram_reels"]).ok

    long = vu.check(_info(seconds=200), pl["instagram_reels"])
    assert long.trim_to == 180.0
    assert vu.check(_info(seconds=200), pl["tiktok"]).ok

    odd = vu.check(_info(vcodec="mpeg4", acodec="mp3", fps="120/1"), pl["tiktok"])
    assert {k for k, _ in odd.issues} == {"video_upload.bad_video_codec",
                                          "video_upload.bad_audio_codec", "video_upload.high_fps"}
    quiet = vu.check(_info(720, 1280, acodec=None), pl["tiktok"])
    assert quiet.ok and {k for k, _ in quiet.notes} == {"video_upload.no_audio"}


@needs_ffmpeg
def test_upload_convert_to_vertical(tmp_path):
    vu = plugin("video_upload")
    src = make_clip(tmp_path / "wide.mkv", size="1280x720", seconds=2,
                    extra=["-c:v", "mpeg4", "-c:a", "libmp3lame"])
    info = media.probe(src)
    result = vu.check(info, vu.load_platforms()["tiktok"])
    out = vu.convert(src, info, result, "tiktok")
    assert out.name == "wide.tiktok.mp4"
    after = media.probe(out)
    assert media.display_size(media.streams(after, "video")[0]) == (1080, 1920)
    assert vu.check(after, vu.load_platforms()["tiktok"]).ok


def test_missing_ffmpeg_is_reported(tmp_path, term, monkeypatch):
    config.set_value("language", "de")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    real_which = shutil.which
    monkeypatch.setattr(media.shutil, "which",
                        lambda name: None if name.startswith("ff") else real_which(name))
    index = [p.id for p in registry.discover()].index("music_check") + 1
    t = term([str(index), "", str(clip), "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Das Programm „ffprobe“ fehlt. In Termux: pkg install ffmpeg" in t.text
