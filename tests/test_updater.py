import shutil
import subprocess

import pytest

from aio.core import config, updater
from aio.core.main import main

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def commit(repo, name, message):
    (repo / name).write_text(message, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """A fake GitHub (upstream) and an installed checkout in AIO_SRC."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-q", "-b", "main")
    commit(upstream, "a.txt", "first")
    src = tmp_path / "src"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{upstream}", str(src)],
                   check=True, capture_output=True)
    monkeypatch.setenv("AIO_SRC", str(src))
    return upstream, src


def no_pip(monkeypatch):
    monkeypatch.setattr(updater, "_pip_commands", lambda src: [["true"]])


@needs_git
def test_up_to_date(repos):
    status = updater.check()
    assert status.error is None and not status.available


@needs_git
def test_finds_and_installs_update(repos):
    upstream, src = repos
    commit(upstream, "b.txt", "second")
    status = updater.check()
    assert status.available and status.subject == "second"
    assert updater.install(status, pip_commands=[["true"]]) is None
    assert (src / "b.txt").exists()
    assert not updater.check().available


def test_no_source_folder():
    assert updater.check().error == "update.error_no_source"


@needs_git
def test_offline_is_reported_not_raised(repos):
    _, src = repos
    git(src, "remote", "set-url", "origin", "file:///does/not/exist")
    assert updater.check().error == "update.error_network"


def test_is_due():
    assert updater.is_due({}) is True
    assert updater.is_due({"update_mode": "off"}) is False
    cfg = {"update_mode": "check", "update_interval_hours": 24, "update_last_check": 1000}
    assert updater.is_due(cfg, now=1000 + 3600) is False
    assert updater.is_due(cfg, now=1000 + 25 * 3600) is True
    assert updater.is_due({"update_interval_hours": 0, "update_last_check": 1000}, now=1000)


@needs_git
def test_settings_update_now(repos, term, monkeypatch):
    upstream, src = repos
    config.set_value("language", "en")
    config.set_value("update_mode", "off")
    commit(upstream, "b.txt", "second")
    no_pip(monkeypatch)
    t = term(["s", "3", "y", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Update available" in t.text and "second" in t.text
    assert "Restart aio" in t.text
    assert (src / "b.txt").exists()


def test_auto_update_setting_is_saved(term):
    config.set_value("language", "de")
    t = term(["s", "4", "3", "3", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    cfg = config.load()
    assert cfg["update_mode"] == "auto" and cfg["update_interval_hours"] == 168
    assert "Gespeichert: Beim Start prüfen und automatisch installieren, höchstens wöchentlich." \
        in t.text


@needs_git
def test_start_notices_update(repos, term):
    upstream, src = repos
    config.set_value("language", "en")
    commit(upstream, "b.txt", "second")
    t = term(["q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "An update is available" in t.text
    assert not (src / "b.txt").exists()  # "check" mode only tells
    assert config.load()["update_last_check"] > 0


@needs_git
def test_start_auto_installs(repos, term, monkeypatch):
    upstream, src = repos
    config.set_value("language", "en")
    config.set_value("update_mode", "auto")
    commit(upstream, "b.txt", "second")
    no_pip(monkeypatch)
    t = term(["q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "AIO was updated" in t.text
    assert (src / "b.txt").exists()


def test_start_offline_stays_quiet(term):
    config.set_value("language", "en")
    t = term(["q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "update" not in t.text.lower()
