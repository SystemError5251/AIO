"""Correction mode: review machine-translated ("_auto") and missing texts.

Corrections never touch the installed locale files (an update would overwrite
them). They go to ~/.aio/locales/<lang>.json, which the translator reads last:

    {"_reviewed": ["menu.quit", ...], "menu.quit": "corrected text", ...}

A key listed in "_reviewed" without a value was accepted as it is. The file can
be shared and merged into the repository with `python -m aio.tools.merge_review`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import config
from aio.tools.translate import AUTO_KEY, read, source_texts, write, placeholders

REVIEWED_KEY = "_reviewed"


@dataclass
class Item:
    key: str
    source: Any          # English text (or plural dict)
    current: Any         # text the user sees now; None = missing, English is shown
    status: str          # "auto" or "missing"


def user_locales_dir() -> Path:
    return config.aio_home() / "locales"


def overlay_path(lang: str) -> Path:
    return user_locales_dir() / f"{lang}.json"


def load_overlay(lang: str) -> dict[str, Any]:
    data = read(overlay_path(lang))
    return data if isinstance(data, dict) else {}


def pending(dirs: list[Path], lang: str) -> list[Item]:
    """Texts in `lang` that a human has not checked yet: machine-made first, then missing."""
    overlay = load_overlay(lang)
    reviewed = set(overlay.get(REVIEWED_KEY, []))
    auto, missing = [], []
    for directory in dirs:
        target = read(directory / f"{lang}.json")
        marked = set(target.get(AUTO_KEY, []))
        for key, source in source_texts(directory).items():
            if key in reviewed:
                continue
            if key in target and key in marked:
                auto.append(Item(key, source, overlay.get(key, target[key]), "auto"))
            elif key not in target and key not in overlay:
                missing.append(Item(key, source, None, "missing"))
    return auto + missing


def check(source: Any, value: Any) -> bool:
    """A correction may not invent placeholders; a plain text must keep all of them."""
    if isinstance(source, dict) != isinstance(value, dict):
        return False
    texts = value.values() if isinstance(value, dict) else [value]
    if not all(isinstance(t, str) and t.strip() for t in texts):
        return False
    if placeholders(value) - placeholders(source):
        return False
    return isinstance(value, dict) or placeholders(value) == placeholders(source)


def _save(lang: str, overlay: dict[str, Any]) -> None:
    path = overlay_path(lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, overlay)


def accept(lang: str, key: str) -> None:
    overlay = load_overlay(lang)
    reviewed = overlay.setdefault(REVIEWED_KEY, [])
    if key not in reviewed:
        reviewed.append(key)
    _save(lang, overlay)


def correct(lang: str, item: Item, value: Any) -> None:
    if not check(item.source, value):
        raise ValueError(item.key)
    overlay = load_overlay(lang)
    overlay[item.key] = value
    _save(lang, overlay)
    accept(lang, item.key)


def merge_overlay(dirs: list[Path], lang: str, overlay: dict[str, Any]) -> tuple[int, list[str]]:
    """Write a (shared) overlay into the locale files. Returns (changed, rejected keys)."""
    changed, rejected = 0, []
    reviewed = list(overlay.get(REVIEWED_KEY, []))
    keys = reviewed + [k for k in overlay if not k.startswith("_") and k not in reviewed]
    for directory in dirs:
        sources = source_texts(directory)
        path = directory / f"{lang}.json"
        target = read(path)
        dirty = False
        for key in keys:
            if key not in sources:
                continue
            if key in overlay:
                if not check(sources[key], overlay[key]):
                    rejected.append(key)
                    continue
                if target.get(key) != overlay[key]:
                    target[key] = overlay[key]
                    dirty = True
            elif key not in target:
                continue  # "accepted" a missing text: nothing to keep
            auto = target.get(AUTO_KEY, [])
            if key in auto:
                auto.remove(key)
                dirty = True
            changed += 1
        if AUTO_KEY in target and not target[AUTO_KEY]:
            del target[AUTO_KEY]
            dirty = True
        if dirty:
            write(path, target)
    return changed, rejected
