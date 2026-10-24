"""System check (`aio --doctor`): which programs, packages and keys the tools need.

Every check says which tools depend on it and how to install it in Termux.
Nothing is installed automatically; the AcoustID key can be entered and
tested here, because there is no other place in the UI for it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from aio.core import media

MIN_PYTHON = (3, 11)
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
ACOUSTID_INVALID_KEY = 4  # AcoustID error code "invalid API key"


@dataclass
class Check:
    name: str
    ok: bool
    tools: list[str] = field(default_factory=list)  # plugin ids that need it
    hint: str = ""                                   # translation key
    values: dict = field(default_factory=dict)       # placeholders for hint
    optional: bool = False


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def storage_dir() -> Path:
    return Path.home() / "storage" / "shared"


def acoustid_key(cfg: dict) -> str | None:
    return os.environ.get("AIO_ACOUSTID_KEY") or cfg.get("acoustid_key") or None


def _program(name: str, tools: list[str], optional: bool = False) -> Check:
    return Check(name, media.has(name), tools, "doctor.install",
                 {"cmd": f"pkg install {media.PACKAGES.get(name, name)}"}, optional)


def run_checks(cfg: dict) -> list[Check]:
    video = ["video_upload", "privacy_strip", "music_check", "subtitles", "loudnorm", "video_crop"]
    version = ".".join(map(str, sys.version_info[:3]))
    checks = [
        Check("python", sys.version_info[:2] >= MIN_PYTHON, [], "doctor.python_old",
              {"version": version}),
        _program("ffmpeg", video),
        _program("ffprobe", video),
        _program("fpcalc", ["music_check"], optional=True),
        Check("acoustid", bool(acoustid_key(cfg)), ["music_check"], "doctor.acoustid_missing",
              optional=True),
        _program("git", ["git_backup"]),
        _program("termux-share", ["video_upload"]),
        _program("termux-clipboard-set", ["secrets_vault"], optional=True),
        _program("qrencode", ["wifi_share"], optional=True),
        Check("cryptography", _module("cryptography"), ["secrets_vault"], "doctor.install",
              {"cmd": "pkg install python-cryptography"}),
        Check("babel", _module("babel"), [], "doctor.install", {"cmd": "pip install babel"},
              optional=True),
        Check("storage", storage_dir().is_dir(), ["storage_clean", "wifi_share"],
              "doctor.storage_missing"),
    ]
    for check in checks:
        if check.name.startswith("termux-") and not check.ok:
            check.hint = "doctor.termux_api"
    return checks


def verify_acoustid_key(key: str, opener=None) -> bool | None:
    """True = key accepted, False = rejected, None = AcoustID not reachable.

    Sends a lookup with a dummy fingerprint: a valid key gets a different
    error (bad fingerprint) or an empty result, an invalid one error code 4.
    """
    opener = opener or urllib.request.urlopen
    body = urllib.parse.urlencode({"client": key, "duration": 10, "fingerprint": "AQAAAA"})
    request = urllib.request.Request(ACOUSTID_URL, data=body.encode())
    try:
        with opener(request, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            data = json.load(exc)
        except (ValueError, OSError):
            return None
    except (urllib.error.URLError, OSError, ValueError):
        return None
    error = data.get("error") or {}
    if data.get("status") == "error" and (error.get("code") == ACOUSTID_INVALID_KEY
                                         or "api key" in str(error.get("message", "")).lower()):
        return False
    return True
