import json

from aio.core import config


def test_defaults_when_missing():
    assert config.load()["language"] is None


def test_roundtrip(aio_home):
    config.set_value("language", "de")
    assert config.load()["language"] == "de"
    assert json.loads((aio_home / "config.json").read_text("utf-8")) == {"language": "de"}


def test_broken_file_falls_back_to_defaults(aio_home):
    aio_home.mkdir(parents=True)
    (aio_home / "config.json").write_text("{not json", "utf-8")
    assert config.load()["language"] is None
