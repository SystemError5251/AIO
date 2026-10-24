"""Lines and rows of the full-screen UI. Nothing here knows about curses.

A screen is a list of rows. Each row draws itself as one or more
:class:`Line` objects made of ``(text, style)`` parts; the curses front end
only paints them. Keys arrive as names: a printable character, or one of
``up``, ``down``, ``left``, ``right``, ``enter``, ``back``, ``backspace``,
``home``, ``end``, ``pageup``, ``pagedown``, ``tab``.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from aio.core.context import display_width

Part = tuple[str, str]


@dataclass
class Line:
    parts: list[Part] = field(default_factory=list)
    item: int | None = None    # index of the selectable row this line belongs to
    fill: str | None = None    # style for the rest of the row (selection bar)
    align: bool = True         # may be right-aligned for right-to-left languages
    cursor: int | None = None  # column of the text cursor

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.parts)

    @property
    def width(self) -> int:
        return display_width(self.text)


def line(text: str = "", style: str = "normal", **kwargs) -> Line:
    return Line([(text, style)], **kwargs)


def clip(text: str, columns: int) -> str:
    """Cut text to a number of terminal columns, wide characters included."""
    if columns <= 0:
        return ""
    if display_width(text) <= columns:
        return text
    out, used = [], 0
    for ch in text:
        w = 0 if unicodedata.combining(ch) else display_width(ch)
        if used + w > columns - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def pad(text: str, columns: int) -> str:
    text = clip(text, columns)
    return text + " " * (columns - display_width(text))


def wrap(text: str, width: int) -> list[str]:
    """Word wrap by terminal columns. Keeps empty lines and indentation and
    breaks inside words that are too long (paths, Chinese or Japanese text)."""
    width = max(4, width)
    out: list[str] = []
    for paragraph in text.split("\n"):
        body = paragraph.lstrip(" ")
        indent = " " * min(len(paragraph) - len(body), width // 2)
        room = width - len(indent)
        current = ""
        for word in body.split(" "):
            while display_width(word) > room:
                if current:
                    out.append(indent + current)
                    current = ""
                head = _take(word, room)
                out.append(indent + head)
                word = word[len(head):]
            if not current:
                current = word
            elif display_width(current) + 1 + display_width(word) <= room:
                current += " " + word
            else:
                out.append(indent + current)
                current = word
        out.append(indent + current if current else "")
    return out


def _take(text: str, columns: int) -> str:
    used = 0
    for i, ch in enumerate(text):
        used += 0 if unicodedata.combining(ch) else display_width(ch)
        if used > columns:
            return text[:max(1, i)]
    return text


def rule(title: str, width: int, style: str = "accent") -> Line:
    """``── TITLE ─────────`` section heading."""
    title = clip(title.upper(), max(1, width - 6))
    rest = max(0, width - display_width(title) - 4)
    return Line([("── ", "frame"), (title, style), (" " + "─" * rest, "frame")])


def box(title: str, body: list[list[Part]], width: int, selected: bool = False,
        fill: str | None = None) -> list[Line]:
    """A rounded frame around some lines of parts."""
    frame = "frame_sel" if selected else "frame"
    inner = max(4, width - 4)
    title = clip(title, max(1, inner - 2))
    top_rest = max(0, width - display_width(title) - 5)
    lines = [Line([("╭─ ", frame), (title, "accent" if selected else "label"),
                   (" " + "─" * top_rest + "╮", frame)], align=False)]
    for parts in body:
        used = sum(display_width(t) for t, _ in parts)
        if used > inner:
            parts = [(clip("".join(t for t, _ in parts), inner), parts[0][1] if parts else "normal")]
            used = inner
        lines.append(Line([("│ ", frame), *parts,
                           (" " * (inner - used), fill or "normal"), (" │", frame)], align=False))
    lines.append(Line([("╰" + "─" * (width - 2) + "╯", frame)], align=False))
    return lines


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #

class Row:
    selectable = True

    def lines(self, width: int, selected: bool) -> list[Line]:
        return []

    def handle(self, key: str) -> str | None:
        """Return an action name for the screen, or None if the key was not used."""
        return None

    def tap(self, x: int, width: int) -> str | None:
        return self.handle("enter")


class Static(Row):
    """Lines that can't be selected: headings, help text, spacing."""

    selectable = False

    def __init__(self, make: Callable[[int], list[Line]] | list[Line] | None = None):
        self.make = make

    def lines(self, width: int, selected: bool) -> list[Line]:
        if self.make is None:
            return [Line()]
        return self.make(width) if callable(self.make) else list(self.make)


class Text(Static):
    """Wrapped paragraph text."""

    def __init__(self, text: str, style: str = "normal", indent: int = 1):
        super().__init__(lambda width: [line(" " * indent + chunk, style)
                                        for chunk in wrap(text, width - indent - 1)])


class Entry(Row):
    """A menu entry: icon, label, optional value on the right and a dimmed
    description underneath. ``left``/``right`` give ``<action>:prev``/``:next``
    when the entry has a value that can be changed in place."""

    def __init__(self, label: str, action: str, desc: str = "", value: str = "",
                 icon: str = "›", style: str = "normal", cycle: bool = False):
        self.label, self.action, self.desc = label, action, desc
        self.value, self.icon, self.style, self.cycle = value, icon, style, cycle

    def handle(self, key: str) -> str | None:
        if key in ("enter", " "):
            return self.action
        if self.cycle and key in ("left", "right"):
            return f"{self.action}:{'prev' if key == 'left' else 'next'}"
        return None

    def tap(self, x: int, width: int) -> str | None:
        if self.cycle:
            return f"{self.action}:{'prev' if x < width // 2 else 'next'}"
        return self.action

    def lines(self, width: int, selected: bool) -> list[Line]:
        value = f"‹ {self.value} ›" if self.cycle and self.value else self.value
        value = clip(value, max(4, (width - 6) // 2)) if value else ""
        room = max(4, width - 4 - (display_width(value) + 2 if value else 0))
        label = clip(self.label, room)
        gap = max(1, width - 4 - display_width(label) - display_width(value) - 1)
        if selected:
            first = Line([(" ▌ ", "cursor"), (label, "selected_bold"), (" " * gap, "selected"),
                          (value, "selected_value")], fill="selected")
        else:
            first = Line([(f" {self.icon} ", "icon"), (label, self.style), (" " * gap, "normal"),
                          (value, "value")])
        out = [first]
        if self.desc and selected:
            for chunk in wrap(self.desc, width - 4)[:4]:
                out.append(Line([(" ▌ ", "cursor"), (chunk, "selected_dim")], fill="selected"))
        elif self.desc:
            out.append(line("   " + clip(self.desc.replace("\n", " "), width - 4), "dim"))
        return out


class Choices:
    """Cycles through a list of ``(value, label)`` options."""

    def __init__(self, options: list[tuple[str, str]], value: str):
        self.options = options
        values = [v for v, _ in options]
        self.index = values.index(value) if value in values else 0

    @property
    def value(self) -> str:
        return self.options[self.index][0]

    @property
    def label(self) -> str:
        return self.options[self.index][1]

    def step(self, delta: int) -> str:
        self.index = (self.index + delta) % len(self.options)
        return self.value
