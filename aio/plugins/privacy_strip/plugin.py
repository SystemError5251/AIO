"""Privacy-Stripper: removes metadata (GPS, device, timestamps) from videos and photos.

JPEG and PNG are cleaned losslessly in pure Python. Videos go through
`ffmpeg -c copy`, so nothing is re-encoded. The original is never touched;
the result is written next to it as `<name>.clean.<ext>`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from aio.core import media

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
SUPPORTED_EXTS = IMAGE_EXTS | media.VIDEO_EXTS

# Container tags that describe the file structure, not the person or device.
HARMLESS_TAGS = {"major_brand", "minor_version", "compatible_brands", "language",
                 "handler_name", "vendor_id", "duration"}


@dataclass
class Result:
    source: Path
    output: Path | None = None
    found: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    error: str | None = None


# --------------------------------------------------------------------------- #
# JPEG
# --------------------------------------------------------------------------- #

def _exif_info(payload: bytes) -> tuple[int, bool]:
    """Return (orientation, has_gps) from an APP1 'Exif' payload."""
    tiff = payload[6:]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return 1, False
    endian = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack_from(endian + "I", tiff, 4)
        (count,) = struct.unpack_from(endian + "H", tiff, ifd)
        orientation, gps = 1, False
        for i in range(count):
            tag, typ, _n, _value = struct.unpack_from(endian + "HHII", tiff, ifd + 2 + 12 * i)
            if tag == 0x0112 and typ == 3:
                (orientation,) = struct.unpack_from(endian + "H", tiff, ifd + 2 + 12 * i + 8)
            elif tag == 0x8825:
                gps = True
        return orientation, gps
    except struct.error:
        return 1, False


def _orientation_segment(orientation: int) -> bytes:
    """Minimal EXIF that only says how to rotate the photo, so it is not shown sideways."""
    tiff = (b"MM\x00\x2a" + struct.pack(">I", 8) + struct.pack(">H", 1)
            + struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0) + struct.pack(">I", 0))
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def strip_jpeg(data: bytes) -> tuple[bytes, list[str]]:
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    out = bytearray(b"\xff\xd8")
    found: list[str] = []
    orientation = 1
    i = 2
    insert_at = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("corrupt JPEG segment")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xDA:  # start of scan: image data follows, copy the rest
            out += data[i:]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += data[i:i + 2]
            i += 2
            continue
        (length,) = struct.unpack_from(">H", data, i + 2)
        segment = data[i:i + 2 + length]
        payload = segment[4:]
        drop = False
        if marker == 0xE1:
            drop = True
            if payload.startswith(b"Exif\x00\x00"):
                orientation, gps = _exif_info(payload)
                found.append("EXIF")
                if gps:
                    found.append("GPS")
            elif payload.startswith(b"http://ns.adobe.com/xap/"):
                found.append("XMP")
            else:
                found.append("APP1")
        elif marker == 0xED:
            drop = True
            found.append("IPTC")
        elif marker == 0xFE:
            drop = True
            found.append("COMMENT")
        elif 0xE3 <= marker <= 0xEF and marker != 0xEE:
            # APP3..APP15 hold maker notes, previews, etc. Keep APP0 (JFIF),
            # APP2 (ICC colour profile) and APP14 (Adobe colour transform).
            drop = True
            found.append(f"APP{marker - 0xE0}")
        if not drop:
            out += segment
            if marker == 0xE0:
                insert_at = len(out)
        i += 2 + length
    if orientation not in (0, 1) and 1 <= orientation <= 8:
        out[insert_at:insert_at] = _orientation_segment(orientation)
    return bytes(out), found


# --------------------------------------------------------------------------- #
# PNG
# --------------------------------------------------------------------------- #

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_METADATA_CHUNKS = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def strip_png(data: bytes) -> tuple[bytes, list[str]]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    out = bytearray(PNG_SIGNATURE)
    found: list[str] = []
    i = len(PNG_SIGNATURE)
    while i + 8 <= len(data):
        (length,) = struct.unpack_from(">I", data, i)
        ctype = data[i + 4:i + 8]
        end = i + 12 + length
        if ctype in PNG_METADATA_CHUNKS:
            found.append(ctype.decode("ascii"))
        else:
            out += data[i:end]
        i = end
        if ctype == b"IEND":
            break
    return bytes(out), found


# --------------------------------------------------------------------------- #
# Video
# --------------------------------------------------------------------------- #

def video_findings(info: dict) -> list[str]:
    """Names of metadata tags that reveal something about person, place or device."""
    found = []
    for key in (info.get("format", {}).get("tags") or {}):
        if key.lower() not in HARMLESS_TAGS:
            found.append(key)
    for stream in info.get("streams", []):
        kind = stream.get("codec_type", "?")
        if kind == "data":
            found.append(f"{kind} stream ({stream.get('codec_tag_string', '?')})")
            continue
        for key in (stream.get("tags") or {}):
            if key.lower() not in HARMLESS_TAGS:
                found.append(f"{kind}:{key}")
    return found


def strip_video(src: Path, dst: Path) -> None:
    args = ["-y", "-i", str(src),
            "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",  # drop data tracks (GPS etc.)
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-c", "copy",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    if dst.suffix.lower() in (".mp4", ".mov", ".m4v", ".3gp"):
        args += ["-movflags", "+faststart"]
    media.ffmpeg([*args, str(dst)])


# --------------------------------------------------------------------------- #
# File / folder handling
# --------------------------------------------------------------------------- #

def clean_file(path: Path) -> Result:
    result = Result(source=path)
    ext = path.suffix.lower()
    try:
        if ext in IMAGE_EXTS:
            stripper = strip_png if ext == ".png" else strip_jpeg
            cleaned, result.found = stripper(path.read_bytes())
            result.output = media.output_path(path, "clean")
            result.output.write_bytes(cleaned)
            _, result.remaining = stripper(cleaned)
            if "EXIF" in result.remaining:  # only our orientation-only EXIF
                result.remaining.remove("EXIF")
        elif ext in media.VIDEO_EXTS:
            result.found = video_findings(media.probe(path))
            result.output = media.output_path(path, "clean")
            strip_video(path, result.output)
            result.remaining = video_findings(media.probe(result.output))
        else:
            result.error = "unsupported"
    except media.MissingTool:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        result.error = str(exc)
        if result.output and result.output.exists():
            result.output.unlink()
        result.output = None
    return result


def collect(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS and ".clean" not in p.stem)


def run(ctx):
    target = ctx.ask_file(ctx.t("privacy_strip.ask_path"), allow_dir=True)
    if target is None:
        return
    files = collect(target)
    if not files:
        ctx.print(ctx.t("privacy_strip.nothing_found"))
        return
    ok = 0
    for path in files:
        ctx.print(f"- {path.name}")
        result = clean_file(path)
        if result.error == "unsupported":
            ctx.print("  " + ctx.t("privacy_strip.unsupported", ext=path.suffix or "?"))
            continue
        if result.error:
            ctx.print("  " + ctx.t("privacy_strip.failed", error=result.error))
            continue
        ok += 1
        if result.found:
            ctx.print("  " + ctx.t("privacy_strip.removed", count=len(result.found),
                                    items=", ".join(result.found)))
        else:
            ctx.print("  " + ctx.t("privacy_strip.already_clean"))
        if result.remaining:
            ctx.print("  " + ctx.t("privacy_strip.remaining", items=", ".join(result.remaining)))
        ctx.print("  " + ctx.t("privacy_strip.saved", path=str(result.output)))
    ctx.print(ctx.t("privacy_strip.summary", count=ok, total=len(files)))
