"""Shared state handed to the UI and to every plugin's run(ctx)."""

from __future__ import annotations

import shutil
import textwrap
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aio.core.i18n import Translator
from aio.core.registry import Plugin


def display_width(text: str) -> int:
    """Terminal columns: combining marks take none, CJK wide characters take two."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch) or unicodedata.category(ch) == "Cf":
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def align_rtl(text: str, columns: int) -> str:
    """Right-align (and wrap) text for right-to-left languages."""
    out = []
    for line in text.splitlines() or [""]:
        for part in textwrap.wrap(line, max(10, columns - 1)) or [""]:
            out.append(" " * max(0, columns - display_width(part)) + part)
    return "\n".join(out)


@dataclass
class AppContext:
    translator: Translator
    config: dict[str, Any]
    plugins: list[Plugin] = field(default_factory=list)
    input_fn: Callable[[str], str] = input
    print_fn: Callable[..., None] = print

    def t(self, key: str, count: int | None = None, **kwargs: Any) -> str:
        return self.translator.t(key, count=count, **kwargs)

    def print(self, text: str = "") -> None:
        """Print one line; right-aligned for RTL languages (flag from _meta.json)."""
        if self.translator.is_rtl and text:
            text = align_rtl(text, shutil.get_terminal_size((80, 24)).columns)
        self.print_fn(text)

    def ask_file(self, prompt: str | None = None, allow_dir: bool = False) -> Path | None:
        """Ask for an existing file (or folder) path; quotes and ~ are handled. None = cancelled."""
        while True:
            answer = self.ask((prompt or self.t("file.prompt")) + " ")
            if not answer:
                return None
            path = Path(answer.strip("'\"")).expanduser()
            if path.is_file() or (allow_dir and path.is_dir()):
                return path
            self.print(self.t("file.not_found", path=str(path)))

    def confirm(self, prompt: str) -> bool:
        """Yes/no question; accepted first letters come from "common.yes_letters"."""
        answer = self.ask(f"{prompt} ({self.t('common.yes_no')}) ")
        return bool(answer) and answer[0].casefold() in self.t("common.yes_letters").casefold()

    def ask(self, prompt: str) -> str | None:
        """Read one line. Returns None on Ctrl+D / Ctrl+C so callers can exit cleanly."""
        try:
            return self.input_fn(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            self.print_fn("")
            return None
