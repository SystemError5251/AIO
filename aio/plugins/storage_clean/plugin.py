"""Speicher-Aufräumer: find what fills the phone and remove the clutter.

Scans a folder for the largest files, exact duplicates (size, then a quick
hash of the start, then a full SHA-256) and cache/temporary files. Nothing is
deleted without showing the list and the total size first. Symlinks are never
followed, so a link cannot lead the scan (or a deletion) somewhere else.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

LARGE_BYTES = 50 * 1024 * 1024
TOP_LARGE = 10
CACHE_DIRS = {".thumbnails", ".cache", "__pycache__", ".trash"}
JUNK_SUFFIXES = (".tmp", ".temp", ".part", ".partial", ".crdownload")
CHUNK = 1024 * 1024


@dataclass
class Scan:
    files: int = 0
    total: int = 0
    large: list[tuple[int, Path]] = field(default_factory=list)
    duplicates: list[list[Path]] = field(default_factory=list)   # each group: keep [0]
    junk: list[tuple[int, Path]] = field(default_factory=list)    # files or cache folders
    unreadable: int = 0

    @property
    def duplicate_bytes(self) -> int:
        return sum(p.stat().st_size * (len(g) - 1) for g in self.duplicates for p in g[:1])

    @property
    def junk_bytes(self) -> int:
        return sum(size for size, _ in self.junk)


def format_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _folder_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def _hash(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        read = 0
        while chunk := fh.read(CHUNK):
            h.update(chunk)
            read += len(chunk)
            if limit and read >= limit:
                break
    return h.hexdigest()


def find_duplicates(by_size: dict[int, list[Path]]) -> list[list[Path]]:
    groups = []
    for size, paths in by_size.items():
        if size == 0 or len(paths) < 2:
            continue
        for stage in (CHUNK, None):          # quick hash of the start, then the full file
            buckets: dict[str, list[Path]] = defaultdict(list)
            for p in paths:
                try:
                    buckets[_hash(p, stage)].append(p)
                except OSError:
                    continue
            paths = [p for b in buckets.values() if len(b) > 1 for p in b]
            if stage is None:
                groups += [sorted(b, key=lambda p: (len(str(p)), str(p)))
                           for b in buckets.values() if len(b) > 1]
    return sorted(groups, key=lambda g: -g[0].stat().st_size * (len(g) - 1))


def scan(root: Path) -> Scan:
    result = Scan()
    by_size: dict[int, list[Path]] = defaultdict(list)
    for current, dirs, files in os.walk(root, followlinks=False):
        here = Path(current)
        for d in list(dirs):
            if d in CACHE_DIRS:
                dirs.remove(d)
                result.junk.append((_folder_size(here / d), here / d))
        for name in files:
            path = here / name
            try:
                st = path.lstat()
            except OSError:
                result.unreadable += 1
                continue
            if not path.is_file() or path.is_symlink():
                continue
            result.files += 1
            result.total += st.st_size
            if name.lower().endswith(JUNK_SUFFIXES):
                result.junk.append((st.st_size, path))
                continue
            by_size[st.st_size].append(path)
            if st.st_size >= LARGE_BYTES:
                result.large.append((st.st_size, path))
    result.large = sorted(result.large, reverse=True)[:TOP_LARGE]
    result.duplicates = find_duplicates(by_size)
    return result


def delete(paths: list[Path]) -> tuple[int, int]:
    """Returns (deleted, failed). Folders are removed with their content."""
    deleted = failed = 0
    for p in paths:
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
            deleted += 1
        except OSError:
            failed += 1
    return deleted, failed


def default_folder() -> Path:
    shared = Path.home() / "storage" / "shared"
    return shared if shared.is_dir() else Path.home()


def _ask_folder(ctx) -> Path | None:
    default = default_folder()
    while True:
        answer = ctx.ask(ctx.t("storage_clean.ask_path", default=str(default)) + " ")
        if answer is None:
            return None
        path = Path(answer.strip("'\"")).expanduser() if answer else default
        if path.is_dir():
            return path
        ctx.print(ctx.t("file.not_found", path=str(path)))


def run(ctx):
    root = _ask_folder(ctx)
    if root is None:
        return
    ctx.print(ctx.t("storage_clean.scanning"))
    result = scan(root)
    ctx.print(ctx.t("storage_clean.summary", count=result.files, size=format_size(result.total)))
    if result.unreadable:
        ctx.print(ctx.t("storage_clean.unreadable", count=result.unreadable))

    ctx.print()
    ctx.print(ctx.t("storage_clean.large_title", size=format_size(LARGE_BYTES)))
    if not result.large:
        ctx.print("  " + ctx.t("storage_clean.none"))
    for size, path in result.large:
        ctx.print(f"  {format_size(size):>9}  {path.relative_to(root)}")

    ctx.print()
    ctx.print(ctx.t("storage_clean.dup_title"))
    if not result.duplicates:
        ctx.print("  " + ctx.t("storage_clean.none"))
    for group in result.duplicates[:10]:
        ctx.print(f"  {format_size(group[0].stat().st_size):>9}  {group[0].relative_to(root)}")
        for extra in group[1:]:
            ctx.print("            = " + str(extra.relative_to(root)))
    if result.duplicates:
        extra = [p for g in result.duplicates for p in g[1:]]
        ctx.print(ctx.t("storage_clean.dup_summary", count=len(extra),
                        size=format_size(result.duplicate_bytes)))
        if ctx.confirm(ctx.t("storage_clean.ask_delete_dups")):
            _report(ctx, *delete(extra))

    ctx.print()
    ctx.print(ctx.t("storage_clean.junk_title"))
    if not result.junk:
        ctx.print("  " + ctx.t("storage_clean.none"))
    for size, path in sorted(result.junk, reverse=True)[:15]:
        ctx.print(f"  {format_size(size):>9}  {path.relative_to(root)}")
    if result.junk:
        ctx.print(ctx.t("storage_clean.junk_summary", count=len(result.junk),
                        size=format_size(result.junk_bytes)))
        if ctx.confirm(ctx.t("storage_clean.ask_delete_junk")):
            _report(ctx, *delete([p for _, p in result.junk]))


def _report(ctx, deleted: int, failed: int) -> None:
    ctx.print(ctx.t("storage_clean.deleted", count=deleted))
    if failed:
        ctx.print(ctx.t("storage_clean.delete_failed", count=failed))
