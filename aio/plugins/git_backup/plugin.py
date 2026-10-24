"""Git-Backup: keep a versioned backup of folders (notes, scripts, configs).

Each backup is a folder that becomes a git repository, optionally with a remote
(GitHub, GitLab, own server) to push to. Running a backup commits every change
with a date and pushes it. Files over 95 MB are left out (GitHub refuses files
over 100 MB) via .git/info/exclude, so a single video cannot break the backup.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import config, media

CONFIG_KEY = "git_backups"
MAX_FILE_BYTES = 95 * 1024 * 1024
IDENTITY = ["-c", "user.name=AIO Backup", "-c", "user.email=aio-backup@localhost"]


@dataclass
class Outcome:
    key: str                    # i18n key of the result
    kwargs: dict[str, Any]
    ok: bool = True


def git(folder: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # safe.directory: Termux sees shared storage as owned by another user.
    cmd = [media.require("git"), "-c", f"safe.directory={folder}", "-C", str(folder), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "git failed")
    return result


def _has_identity(folder: Path) -> bool:
    return bool(git(folder, "config", "user.email", check=False).stdout.strip())


def backups() -> list[dict[str, str]]:
    return [b for b in config.load().get(CONFIG_KEY, []) if isinstance(b, dict) and b.get("path")]


def save_backups(items: list[dict[str, str]]) -> None:
    config.set_value(CONFIG_KEY, items)


def setup(folder: Path, remote: str | None) -> None:
    """Make `folder` a repository (if needed) and register it."""
    if not (folder / ".git").exists():
        git(folder, "init", "-q")
        git(folder, "symbolic-ref", "HEAD", "refs/heads/main")
    if remote:
        if git(folder, "remote", "get-url", "origin", check=False).returncode == 0:
            git(folder, "remote", "set-url", "origin", remote)
        else:
            git(folder, "remote", "add", "origin", remote)
    items = [b for b in backups() if Path(b["path"]) != folder]
    items.append({"path": str(folder), "remote": remote or ""})
    save_backups(items)


def exclude_large(folder: Path) -> list[str]:
    """Add files above MAX_FILE_BYTES to .git/info/exclude; returns the new entries."""
    exclude = folder / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    known = set(exclude.read_text("utf-8").splitlines()) if exclude.exists() else set()
    new = []
    for path in folder.rglob("*"):
        if ".git" in path.relative_to(folder).parts or not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            entry = "/" + path.relative_to(folder).as_posix()
            if entry not in known:
                new.append(entry)
    if new:
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(new) + "\n")
    return new


def run_backup(folder: Path, push: bool, now: _dt.datetime | None = None) -> list[Outcome]:
    if not (folder / ".git").exists():
        return [Outcome("git_backup.not_a_repo", {"path": str(folder)}, ok=False)]
    out = []
    skipped = exclude_large(folder)
    if skipped:
        out.append(Outcome("git_backup.skipped_large", {"count": len(skipped),
                                                         "files": ", ".join(skipped[:5])}))
    git(folder, "add", "-A")
    changed = [line for line in git(folder, "status", "--porcelain").stdout.splitlines() if line]
    if changed:
        stamp = (now or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
        identity = [] if _has_identity(folder) else IDENTITY
        git(folder, *identity, "commit", "-q", "-m", f"AIO-Backup {stamp}")
        out.append(Outcome("git_backup.committed", {"count": len(changed)}))
    else:
        out.append(Outcome("git_backup.no_changes", {}))
    if push:
        result = git(folder, "push", "-q", "-u", "origin", "HEAD", check=False)
        if result.returncode == 0:
            out.append(Outcome("git_backup.pushed", {}))
        else:
            detail = (result.stderr or result.stdout).strip().splitlines()
            out.append(Outcome("git_backup.push_failed", {"error": detail[-1] if detail else "?"}, ok=False))
    return out


def _new_backup(ctx) -> None:
    folder = ctx.ask_file(ctx.t("git_backup.ask_folder"), allow_dir=True)
    if folder is None or not folder.is_dir():
        return
    folder = folder.resolve()
    ctx.print(ctx.t("git_backup.remote_hint"))
    remote = ctx.ask(ctx.t("git_backup.ask_remote") + " ")
    if remote is None:
        return
    try:
        setup(folder, remote or None)
    except RuntimeError as exc:
        ctx.print(ctx.t("git_backup.failed", error=str(exc)))
        return
    ctx.print(ctx.t("git_backup.added", path=str(folder)))
    _backup(ctx, {"path": str(folder), "remote": remote})


def _backup(ctx, item: dict[str, str]) -> None:
    ctx.print(f"[{item['path']}]")
    try:
        outcomes = run_backup(Path(item["path"]), push=bool(item.get("remote")))
    except RuntimeError as exc:
        ctx.print("  " + ctx.t("git_backup.failed", error=str(exc)))
        return
    for o in outcomes:
        ctx.print(("  ✓ " if o.ok else "  ✗ ") + ctx.t(o.key, **o.kwargs))


def run(ctx):
    media.require("git")
    while True:
        items = backups()
        ctx.print()
        if items:
            ctx.print(ctx.t("git_backup.list_title"))
            for i, item in enumerate(items, 1):
                target = item.get("remote") or ctx.t("git_backup.local_only")
                ctx.print(f"   {i}) {item['path']}  → {target}")
            ctx.print("   a) " + ctx.t("git_backup.all"))
        else:
            ctx.print(ctx.t("git_backup.none_yet"))
        ctx.print("   n) " + ctx.t("git_backup.new"))
        if items:
            ctx.print("   r) " + ctx.t("git_backup.remove"))
        ctx.print("   b) " + ctx.t("menu.back"))
        answer = (ctx.ask(ctx.t("menu.prompt") + " ") or "b").lower()
        if answer in ("b", "q"):
            return
        if answer == "n":
            _new_backup(ctx)
        elif answer == "a" and items:
            for item in items:
                _backup(ctx, item)
        elif answer == "r" and items:
            pick = ctx.ask(ctx.t("git_backup.remove_prompt") + " ")
            if pick and pick.isdigit() and 1 <= int(pick) <= len(items):
                removed = items.pop(int(pick) - 1)
                save_backups(items)
                ctx.print(ctx.t("git_backup.removed", path=removed["path"]))
        elif answer.isdigit() and 1 <= int(answer) <= len(items):
            _backup(ctx, items[int(answer) - 1])
        else:
            ctx.print(ctx.t("menu.invalid"))
