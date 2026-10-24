"""Screens of the full-screen UI and the controller that switches between them.

No curses in here, so every screen can be tested by feeding key names.
Dialogs that ask questions line by line (running a tool, updates, review,
plugins, system check) are handed to the front end with
:meth:`Controller.run_external`; it leaves full-screen mode, runs them and
comes back.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aio.core import config
from aio.core.context import AppContext, display_width
from aio.core.i18n import available_languages
from aio.core.registry import Plugin
from aio.core.tui.widgets import Entry, Line, Row, Static, Text, box, clip, line, rule, wrap

CATEGORY_ORDER = ("video", "daily", "network", "security", "misc", "demo")
UI_MODES = ("full", "plain")


def _is_typed(key: str) -> bool:
    return len(key) == 1 and key.isprintable()


class Screen:
    def __init__(self, app: "Controller"):
        self.app = app
        self.selected = 0

    # -- what a screen defines ------------------------------------------------

    def title(self) -> str:
        return ""

    def hints(self) -> list[tuple[str, str]]:
        return [("↑↓", self.app.t("tui.key_move")), ("⏎", self.app.t("tui.key_open")),
                ("esc", self.app.t("tui.key_back"))]

    def rows(self) -> list[Row]:
        return []

    def on_action(self, action: str) -> None:
        pass

    def on_key(self, key: str) -> None:
        pass

    def on_back(self) -> None:
        self.app.pop()

    # -- shared behaviour -----------------------------------------------------

    def selectables(self) -> list[Row]:
        return [row for row in self.rows() if row.selectable]

    def move(self, delta: int) -> None:
        count = len(self.selectables())
        if count:
            self.selected = max(0, min(count - 1, self.selected + delta))

    def handle(self, key: str) -> None:
        rows = self.selectables()
        if self.selected >= len(rows):
            self.selected = max(0, len(rows) - 1)
        steps = {"up": -1, "down": 1, "tab": 1, "pageup": -5, "pagedown": 5,
                 "home": -10_000, "end": 10_000}
        if key in steps:
            self.move(steps[key])
            return
        action = rows[self.selected].handle(key) if rows else None
        if action is not None:
            self.on_action(action)
        elif key == "back":
            self.on_back()
        else:
            self.on_key(key)

    def tap(self, item: int, x: int, width: int) -> None:
        """A tap selects a row; tapping the selected row again opens it."""
        rows = self.selectables()
        if not 0 <= item < len(rows):
            return
        if item == self.selected:
            action = rows[item].tap(x, width)
            if action is not None:
                self.on_action(action)
        else:
            self.selected = item

    def render(self, width: int) -> list[Line]:
        out: list[Line] = []
        index = 0
        for row in self.rows():
            if row.selectable:
                chunk = row.lines(width, index == self.selected)
                for item_line in chunk:
                    item_line.item = index
                index += 1
            else:
                chunk = row.lines(width, False)
            out.extend(chunk)
        return out


class LanguageSwitch(Row):
    """The language box at the top of the main screen: ◀ ▶ switch right away,
    enter (or a tap in the middle) opens the full list with search."""

    def __init__(self, app: "Controller"):
        self.app = app

    def handle(self, key: str) -> str | None:
        return {"left": "lang:prev", "right": "lang:next",
                "enter": "lang:pick", " ": "lang:pick"}.get(key)

    def tap(self, x: int, width: int) -> str | None:
        if x < width // 3:
            return "lang:prev"
        if x >= width * 2 // 3:
            return "lang:next"
        return "lang:pick"

    def lines(self, width: int, selected: bool) -> list[Line]:
        app = self.app
        lang = app.language_info(app.language)
        title = app.t("tui.language")
        if app.language != "en":
            title += " · Language"
        name = lang["name"]
        if lang["english_name"] != name:
            name += f"  ({lang['english_name']})"
        inner = max(10, width - 4)
        name = clip(name, inner - 8)
        left = max(0, (inner - display_width(name) - 8) // 2)
        arrow = "accent" if selected else "frame"
        main = [(" " * left, "normal"), ("◀   ", arrow),
                (name, "selected_bold" if selected else "label"), ("   ▶", arrow)]
        hint = app.t("tui.language_hint")
        position = f"{app.language_index() + 1}/{len(app.langs)} · "
        hint = position + hint if display_width(position + hint) <= inner else clip(hint, inner)
        hint_left = max(0, (inner - display_width(hint)) // 2)
        return box(title, [main, [(" " * hint_left + hint, "dim")]], width, selected)


# --------------------------------------------------------------------------- #
# Screens
# --------------------------------------------------------------------------- #

class HomeScreen(Screen):
    """Language switch first (selected on every start), then the tools by category."""

    def title(self) -> str:
        return self.app.t("app.title")

    def hints(self) -> list[tuple[str, str]]:
        t = self.app.t
        return [("◀▶", t("tui.key_language")), ("⏎", t("tui.key_open")), ("s", t("menu.settings")), ("q", t("tui.key_quit"))]

    def plugins(self) -> list[Plugin]:
        order = {name: i for i, name in enumerate(CATEGORY_ORDER)}
        return sorted(self.app.ctx.plugins,
                      key=lambda p: order.get(p.category, order["misc"]))

    def rows(self) -> list[Row]:
        app = self.app
        t = app.t
        rows: list[Row] = [LanguageSwitch(app), Static()]
        plugins = self.plugins()
        if not plugins:
            rows.append(Text(t("menu.no_tools"), "dim"))
        category = None
        for number, plugin in enumerate(plugins, 1):
            if plugin.category != category:
                category = plugin.category
                if number > 1:
                    rows.append(Static())
                label = app.category_name(category)
                rows.append(Static(lambda width, label=label: [rule(label, width)]))
            icon = f"{number}" if number <= 9 else "›"
            rows.append(Entry(t(plugin.name_key), f"tool:{number - 1}",
                              desc=t(plugin.desc_key), icon=icon))
        rows.append(Static())
        rows.append(Static(lambda width: [Line([("─" * width, "frame")], align=False)]))
        rows.append(Entry(t("menu.settings"), "settings", icon="≡"))
        rows.append(Entry(t("menu.quit"), "quit", icon="×"))
        return rows

    def open_tool(self, index: int) -> None:
        plugins = self.plugins()
        if 0 <= index < len(plugins):
            self.app.push(ToolScreen(self.app, plugins[index]))

    def on_action(self, action: str) -> None:
        app = self.app
        if action == "lang:prev":
            app.cycle_language(-1)
        elif action == "lang:next":
            app.cycle_language(1)
        elif action == "lang:pick":
            app.push(LanguageScreen(app))
        elif action.startswith("tool:"):
            self.open_tool(int(action.split(":", 1)[1]))
        elif action == "settings":
            app.push(SettingsScreen(app))
        elif action == "quit":
            app.quit()

    def on_key(self, key: str) -> None:
        if key in ("q", "Q"):
            self.app.quit()
        elif key in ("s", "S"):
            self.app.push(SettingsScreen(self.app))
        elif key in ("l", "L"):
            self.app.push(LanguageScreen(self.app))
        elif key.isdigit() and key != "0":
            self.open_tool(int(key) - 1)

    def on_back(self) -> None:
        pass  # esc on the main screen does nothing, so a stray tap can't quit


class LanguageScreen(Screen):
    """Every language in its own script. Typing filters, enter takes it."""

    def __init__(self, app: "Controller", first: bool = False):
        super().__init__(app)
        self.first = first
        self.query = ""
        codes = [lang["code"] for lang in self.shown()]
        self.selected = codes.index(app.language) if app.language in codes else 0

    def title(self) -> str:
        return self.app.t("picker.title")

    def hints(self) -> list[tuple[str, str]]:
        t = self.app.t
        return [("abc", t("tui.key_search")), ("↑↓", t("tui.key_move")),
                ("⏎", t("tui.key_choose")), ("esc", t("tui.key_back"))]

    def shown(self) -> list[dict[str, Any]]:
        from aio.core.ui.language_picker import filter_languages
        return filter_languages(self.app.langs, self.query)

    def rows(self) -> list[Row]:
        app = self.app
        t = app.t
        rows: list[Row] = []
        if app.language != "en":
            english = app.t_in("en", "picker.title")
            rows.append(Static(lambda width: [line(" " + english, "dim")]))
        rows.append(Static(self._search_box))
        langs = self.shown()
        if not langs:
            rows.append(Text(t("picker.no_match"), "warn"))
        for lang in langs:
            current = lang["code"] == app.language
            english = lang["english_name"] if lang["english_name"] != lang["name"] else ""
            value = f"{english}  {lang['code'].upper()}".strip()
            rows.append(Entry(lang["name"], f"lang:{lang['code']}", value=value,
                              icon="●" if current else "○",
                              style="accent" if current else "normal"))
        return rows

    def _search_box(self, width: int) -> list[Line]:
        t = self.app.t
        text = self.query or t("tui.search_hint")
        lines = box(t("tui.search"), [[("⌕ ", "accent"), (text, "normal" if self.query else "dim")]],
                    width, selected=bool(self.query))
        lines[1].cursor = 4 + display_width(self.query)
        return lines

    def handle(self, key: str) -> None:
        if _is_typed(key) and key != " ":
            self.query += key
            self.selected = 0
        elif key == "backspace":
            self.query = self.query[:-1]
            self.selected = 0
        else:
            super().handle(key)

    def on_action(self, action: str) -> None:
        if action.startswith("lang:"):
            self.app.choose_language(action.split(":", 1)[1], first=self.first)

    def on_back(self) -> None:
        if self.query:
            self.query = ""
            self.selected = 0
        elif self.first:
            self.app.quit(1)  # aborted on first start: nothing chosen, nothing saved
        else:
            self.app.pop()


class ToolScreen(Screen):
    def __init__(self, app: "Controller", plugin: Plugin):
        super().__init__(app)
        self.plugin = plugin

    def title(self) -> str:
        return self.app.t(self.plugin.name_key)

    def rows(self) -> list[Row]:
        app, plugin = self.app, self.plugin
        t = app.t
        origin = t("plugins.builtin" if plugin.builtin else "plugins.user")
        meta = [(" " + app.category_name(plugin.category), "accent"),
                (f"  ·  v{plugin.version}  ·  {origin}", "dim")]
        def about(width: int) -> list[Line]:
            body = [[(chunk, "normal")] for chunk in wrap(t(plugin.help_key), width - 4)]
            return box(t("tui.about"), body, width)

        return [
            Static([Line(meta)]),
            Static(),
            Static(about),
            Static(),
            Entry(t("tui.start"), "start", icon="▶", style="accent"),
            Entry(t("menu.back"), "back", icon="‹"),
        ]

    def on_action(self, action: str) -> None:
        if action == "start":
            from aio.core.ui.menu import run_tool
            self.app.run_external(lambda: run_tool(self.app.ctx, self.plugin), self.title())
        elif action == "back":
            self.app.pop()


class TextScreen(Screen):
    def __init__(self, app: "Controller", title: str, text: str):
        super().__init__(app)
        self._title, self.text = title, text

    def title(self) -> str:
        return self._title

    def rows(self) -> list[Row]:
        return [Text(self.text), Static(), Entry(self.app.t("menu.back"), "back", icon="‹")]

    def on_action(self, action: str) -> None:
        self.app.pop()


class SettingsScreen(Screen):
    def title(self) -> str:
        return self.app.t("settings.title")

    def rows(self) -> list[Row]:
        from aio.core.ui.review import open_count
        from aio.core.ui.update import describe

        app = self.app
        ctx, t = app.ctx, app.t
        pending = open_count(ctx)
        return [
            Entry(t("settings.language"), "language", cycle=True,
                  value=app.language_info(app.language)["name"]),
            Entry(t("settings.ui"), "ui", cycle=True, value=t(f"ui.mode_{app.ui_mode()}")),
            Entry(t("settings.display_help"), "help"),
            Static(),
            Entry(t("settings.update_now"), "update"),
            Entry(t("settings.auto_update"), "auto", value=describe(ctx)),
            Entry(t("settings.review"), "review", value=str(pending) if pending else ""),
            Entry(t("settings.plugins"), "plugins", value=str(len(ctx.plugins))),
            Entry(t("settings.doctor"), "doctor"),
            Static(),
            Entry(t("menu.back"), "back", icon="‹"),
        ]

    def on_action(self, action: str) -> None:
        from aio.core.ui.doctor import system_check
        from aio.core.ui.plugins import manage_plugins
        from aio.core.ui.review import review_translations
        from aio.core.ui.update import auto_update_settings, update_now

        app = self.app
        ctx, t = app.ctx, app.t
        external: dict[str, tuple[str, Callable[..., Any]]] = {
            "update": ("settings.update_now", update_now),
            "auto": ("settings.auto_update", auto_update_settings),
            "review": ("settings.review", review_translations),
            "plugins": ("settings.plugins", manage_plugins),
            "doctor": ("settings.doctor", system_check),
        }
        if action in ("language:prev", "language:next"):
            app.cycle_language(-1 if action.endswith("prev") else 1)
        elif action == "language":
            app.push(LanguageScreen(app))
        elif action.startswith("ui"):
            app.toggle_ui_mode()
        elif action == "help":
            app.push(TextScreen(app, t("settings.display_help"), t("help.display")))
        elif action in external:
            key, job = external[action]
            app.run_external(lambda: job(ctx), t(key))
        elif action == "back":
            app.pop()

    def on_key(self, key: str) -> None:
        if key in ("q", "b"):
            self.app.pop()


# --------------------------------------------------------------------------- #
# Controller
# --------------------------------------------------------------------------- #

class Controller:
    def __init__(self, ctx: AppContext, first_start: bool = False, open_picker: bool = False):
        self.ctx = ctx
        self.langs = available_languages()
        self.running = True
        self.exit_code = 0
        self.pending: tuple[Callable[[], Any], str] | None = None
        self.status: tuple[str, str] = ("", "dim")
        self.stack: list[Screen] = [LanguageScreen(self, first=True) if first_start
                                    else HomeScreen(self)]
        if open_picker and not first_start:
            self.push(LanguageScreen(self))

    # -- texts and languages --------------------------------------------------

    def t(self, key: str, count: int | None = None, **kwargs: Any) -> str:
        return self.ctx.t(key, count=count, **kwargs)

    def t_in(self, lang: str, key: str) -> str:
        translator = self.ctx.translator
        previous = translator.language
        translator.language = lang
        try:
            return translator.t(key)
        finally:
            translator.language = previous

    @property
    def language(self) -> str:
        return self.ctx.translator.language

    @property
    def rtl(self) -> bool:
        return self.ctx.translator.is_rtl

    def language_info(self, code: str) -> dict[str, Any]:
        for lang in self.langs:
            if lang["code"] == code:
                return lang
        return {"code": code, "name": code, "english_name": code, "dir": "ltr"}

    def language_index(self) -> int:
        codes = [lang["code"] for lang in self.langs]
        return codes.index(self.language) if self.language in codes else 0

    def category_name(self, category: str) -> str:
        key = f"category.{category}"
        return self.t(key) if self.ctx.translator.has(key) or self.ctx.translator.has(key, "en") \
            else category.capitalize()

    def set_language(self, code: str) -> None:
        self.ctx.translator.language = code
        self.ctx.config = config.set_value("language", code)
        self.status = (self.t("settings.language_changed",
                              language=self.language_info(code)["name"]), "ok")

    def cycle_language(self, delta: int) -> None:
        if self.langs:
            self.set_language(self.langs[(self.language_index() + delta) % len(self.langs)]["code"])

    def choose_language(self, code: str, first: bool = False) -> None:
        self.set_language(code)
        if first:
            self.stack = [HomeScreen(self)]
        else:
            self.pop()

    def ui_mode(self) -> str:
        mode = self.ctx.config.get("ui", "full")
        return mode if mode in UI_MODES else "full"

    def toggle_ui_mode(self) -> None:
        mode = "plain" if self.ui_mode() == "full" else "full"
        self.ctx.config = config.set_value("ui", mode)
        self.status = (self.t("ui.changed", mode=self.t(f"ui.mode_{mode}")), "ok")

    # -- navigation -----------------------------------------------------------

    @property
    def screen(self) -> Screen:
        return self.stack[-1]

    def push(self, screen: Screen) -> None:
        self.stack.append(screen)

    def pop(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    def handle(self, key: str) -> None:
        self.status = ("", "dim")
        self.screen.handle(key)

    def tap(self, item: int, x: int, width: int) -> None:
        self.status = ("", "dim")
        self.screen.tap(item, x, width)

    def render(self, width: int) -> list[Line]:
        return self.screen.render(width)

    def run_external(self, job: Callable[[], Any], title: str) -> None:
        """Leave full-screen mode, run a line-by-line dialog, then come back."""
        self.pending = (job, title)
        self.running = False

    def take_pending(self) -> tuple[Callable[[], Any], str] | None:
        pending, self.pending = self.pending, None
        if pending:
            self.running = True
        return pending

    def quit(self, code: int = 0) -> None:
        self.exit_code = code
        self.running = False
