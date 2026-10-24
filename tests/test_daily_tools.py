import datetime as dt
import os
import subprocess

import pytest

from aio.core import config, registry
from aio.core.main import main

needs_git = pytest.mark.skipif(subprocess.run(["which", "git"], capture_output=True).returncode,
                               reason="git not installed")


def plugin(pid):
    return {p.id: p for p in registry.discover()}[pid].load()


def index(pid):
    return str([p.id for p in registry.discover()].index(pid) + 1)


# -- storage cleaner -------------------------------------------------------- #

@pytest.fixture
def messy(tmp_path):
    root = tmp_path / "shared"
    (root / "DCIM" / ".thumbnails").mkdir(parents=True)
    (root / "DCIM" / ".thumbnails" / "t1.jpg").write_bytes(b"x" * 3000)
    (root / "Download").mkdir()
    (root / "DCIM" / "a.jpg").write_bytes(b"same" * 1000)
    (root / "Download" / "a (1).jpg").write_bytes(b"same" * 1000)
    (root / "Download" / "nearly.jpg").write_bytes(b"same" * 999 + b"diff")  # same size, other content
    (root / "Download" / "film.mp4.part").write_bytes(b"p" * 500)
    (root / "Download" / "empty1").touch()
    (root / "Download" / "empty2").touch()
    os.symlink(root / "DCIM", root / "link_to_dcim")
    return root


def test_scan_finds_duplicates_junk_and_ignores_links(messy):
    sc = plugin("storage_clean")
    result = sc.scan(messy)
    assert [[p.name for p in g] for g in result.duplicates] == [["a.jpg", "a (1).jpg"]]
    assert result.duplicate_bytes == 4000
    assert sorted(p.name for _, p in result.junk) == [".thumbnails", "film.mp4.part"]
    assert result.junk_bytes == 3500
    assert result.files == 6  # link not followed, thumbnails folder counted as junk only


def test_large_files_are_listed(messy, monkeypatch):
    sc = plugin("storage_clean")
    monkeypatch.setattr(sc, "LARGE_BYTES", 3500)
    assert sorted(p.name for _, p in sc.scan(messy).large) == ["a (1).jpg", "a.jpg", "nearly.jpg"]


@pytest.mark.parametrize("n,text", [(0, "0 B"), (1023, "1023 B"), (1536, "1.5 KB"),
                                    (5 * 1024 ** 2, "5.0 MB"), (3 * 1024 ** 3, "3.0 GB")])
def test_format_size(n, text):
    assert plugin("storage_clean").format_size(n) == text


def test_storage_clean_end_to_end(messy, term):
    config.set_value("language", "en")
    t = term([index("storage_clean"), "", str(messy), "y", "n", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "1 unneeded copy, 3.9 KB in total." in t.text
    assert "1 deleted." in t.text
    assert (messy / "DCIM" / "a.jpg").exists() and not (messy / "Download" / "a (1).jpg").exists()
    assert (messy / "DCIM" / ".thumbnails").exists()  # junk answer was "n"
    assert (messy / "DCIM").is_dir() and (messy / "link_to_dcim").is_symlink()


# -- git backup ------------------------------------------------------------- #

def _git(folder, *args):
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True,
                          check=True).stdout


@needs_git
def test_backup_commits_and_pushes(tmp_path):
    gb = plugin("git_backup")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "todo.md").write_text("- milk\n")
    gb.setup(notes, str(remote))
    assert gb.backups() == [{"path": str(notes), "remote": str(remote)}]
    out = gb.run_backup(notes, push=True, now=dt.datetime(2026, 10, 24, 9, 30))
    assert [o.key for o in out] == ["git_backup.committed", "git_backup.pushed"]
    assert _git(remote, "log", "--format=%s", "main").strip() == "AIO-Backup 2026-10-24 09:30"
    assert [o.key for o in gb.run_backup(notes, push=False)] == ["git_backup.no_changes"]


@needs_git
def test_backup_leaves_out_large_files(tmp_path, monkeypatch):
    gb = plugin("git_backup")
    monkeypatch.setattr(gb, "MAX_FILE_BYTES", 100)
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "small.txt").write_text("hi")
    (folder / "big.bin").write_bytes(b"x" * 200)
    gb.setup(folder, None)
    out = gb.run_backup(folder, push=False)
    assert out[0].key == "git_backup.skipped_large" and out[0].kwargs["files"] == "/big.bin"
    assert _git(folder, "ls-files").split() == ["small.txt"]
    assert gb.exclude_large(folder) == []  # not added twice


@needs_git
def test_backup_reports_push_failure(tmp_path):
    gb = plugin("git_backup")
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    gb.setup(folder, str(tmp_path / "missing.git"))
    out = gb.run_backup(folder, push=True)
    assert out[-1].key == "git_backup.push_failed" and not out[-1].ok


@needs_git
def test_git_backup_menu_end_to_end(tmp_path, term):
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "run.sh").write_text("echo hi\n")
    config.set_value("language", "en")
    t = term([index("git_backup"), "", "n", str(folder), "", "r", "1", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert f"Backup added: {folder.resolve()}" in t.text
    assert "1 change saved." in t.text
    assert "Removed from the list" in t.text
    assert config.load()["git_backups"] == []
    assert (folder / ".git").is_dir()
