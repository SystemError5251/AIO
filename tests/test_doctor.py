import io
import json
import urllib.error

import pytest

from aio.core import config, doctor, media
from aio.core.main import main


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answering(data):
    return lambda request, timeout: Response(json.dumps(data).encode())


@pytest.fixture
def nothing_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(media, "has", lambda name: False)
    monkeypatch.setattr(doctor, "_module", lambda name: False)
    monkeypatch.setattr(doctor, "storage_dir", lambda: tmp_path / "missing")
    monkeypatch.delenv("AIO_ACOUSTID_KEY", raising=False)


def test_checks_name_install_commands(nothing_installed):
    checks = {c.name: c for c in doctor.run_checks({})}
    assert checks["ffprobe"].values == {"cmd": "pkg install ffmpeg"}
    assert checks["fpcalc"].values == {"cmd": "pkg install chromaprint"} and checks["fpcalc"].optional
    assert checks["termux-clipboard-set"].hint == "doctor.termux_api"
    assert checks["termux-clipboard-set"].values == {"cmd": "pkg install termux-api"}
    assert checks["cryptography"].values == {"cmd": "pkg install python-cryptography"}
    assert not checks["storage"].ok and checks["python"].ok
    assert doctor.run_checks({"acoustid_key": "k"})[4].ok


def test_acoustid_key_check():
    assert doctor.verify_acoustid_key("bad", answering(
        {"status": "error", "error": {"code": 4, "message": "invalid API key"}})) is False
    assert doctor.verify_acoustid_key("good", answering(
        {"status": "error", "error": {"code": 3, "message": "invalid fingerprint"}})) is True
    assert doctor.verify_acoustid_key("good", answering({"status": "ok", "results": []})) is True

    def down(request, timeout):
        raise urllib.error.URLError("offline")

    assert doctor.verify_acoustid_key("x", down) is None


def test_doctor_cli_reports_and_saves_key(nothing_installed, monkeypatch, term):
    monkeypatch.setattr(doctor, "verify_acoustid_key", lambda key: key == "good")
    config.set_value("language", "en")
    t = term(["bad"])
    assert main(["--doctor"], input_fn=t.input, print_fn=t.print, interactive=True) == 1
    assert "✗ ffmpeg" in t.text and "○ qrencode" in t.text
    assert "Install: pkg install termux-api, plus the Termux:API app (F-Droid)." in t.text
    assert "AcoustID rejected the key" in t.text and "acoustid_key" not in config.load()
    t = term(["good"])
    main(["--doctor"], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Key works and is saved." in t.text and config.load()["acoustid_key"] == "good"


def test_doctor_all_ok(monkeypatch, tmp_path, term):
    monkeypatch.setattr(media, "has", lambda name: True)
    monkeypatch.setattr(doctor, "_module", lambda name: True)
    monkeypatch.setattr(doctor, "storage_dir", lambda: tmp_path)
    config.set_value("language", "en")
    config.set_value("acoustid_key", "k")
    t = term([])
    assert main(["--doctor"], input_fn=t.input, print_fn=t.print, interactive=False) == 0
    assert "Everything required is there." in t.text and "✗" not in t.text


def test_settings_entry(nothing_installed, term):
    config.set_value("language", "de")
    t = term(["s", "7", "", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "7) Systemcheck" in t.text and "== Systemcheck ==" in t.text
