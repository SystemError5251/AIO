"""The curses front end: reads keys and taps, paints what the screens return.

curses ships with Python (Termux's ``python`` package included), so nothing
has to be compiled. In Termux a tap selects a row and tapping it again opens
it; the arrow keys and ESC of the extra-keys bar work as well.
"""

from __future__ import annotations

import locale
import os
import sys

from aio.core.context import AppContext, display_width
from aio.core.tui.screens import Controller
from aio.core.tui.widgets import Line, clip, pad

# style -> (foreground, background) for 256 colours, the same for 8 colours, extra attributes
STYLES: dict[str, tuple[tuple[int, int], tuple[str, str], tuple[str, ...]]] = {
    "normal": ((-1, -1), ("", ""), ()),
    "header": ((16, 44), ("BLACK", "CYAN"), ("A_BOLD",)),
    "header_dim": ((23, 44), ("BLACK", "CYAN"), ()),
    "badge": ((231, 24), ("WHITE", "BLUE"), ("A_BOLD",)),
    "accent": ((81, -1), ("CYAN", ""), ("A_BOLD",)),
    "label": ((255, -1), ("WHITE", ""), ("A_BOLD",)),
    "icon": ((44, -1), ("CYAN", ""), ()),
    "value": ((110, -1), ("BLUE", ""), ()),
    "dim": ((245, -1), ("WHITE", ""), ("A_DIM",)),
    "frame": ((240, -1), ("WHITE", ""), ("A_DIM",)),
    "frame_sel": ((44, -1), ("CYAN", ""), ()),
    "cursor": ((81, 24), ("BLACK", "CYAN"), ("A_BOLD",)),
    "selected": ((231, 24), ("BLACK", "CYAN"), ()),
    "selected_bold": ((231, 24), ("BLACK", "CYAN"), ("A_BOLD",)),
    "selected_dim": ((152, 24), ("BLACK", "CYAN"), ()),
    "selected_value": ((159, 24), ("BLACK", "CYAN"), ()),
    "key": ((16, 81), ("BLACK", "CYAN"), ("A_BOLD",)),
    "ok": ((114, -1), ("GREEN", ""), ()),
    "warn": ((221, -1), ("YELLOW", ""), ()),
    "error": ((203, -1), ("RED", ""), ("A_BOLD",)),
}

POLL_MS = 250


def key_name(ch: object) -> str | None:
    """Turn what ``get_wch`` returns into the key names the screens use."""
    import curses

    if isinstance(ch, str):
        special = {"\n": "enter", "\r": "enter", "\x1b": "back", "\t": "tab",
                   "\x7f": "backspace", "\x08": "backspace"}
        if ch in special:
            return special[ch]
        return ch if ch.isprintable() else None
    names = {
        curses.KEY_UP: "up", curses.KEY_DOWN: "down", curses.KEY_LEFT: "left",
        curses.KEY_RIGHT: "right", curses.KEY_ENTER: "enter", curses.KEY_BACKSPACE: "backspace",
        curses.KEY_HOME: "home", curses.KEY_END: "end", curses.KEY_PPAGE: "pageup",
        curses.KEY_NPAGE: "pagedown", curses.KEY_BTAB: "up", curses.KEY_RESIZE: "resize",
        curses.KEY_MOUSE: "mouse",
    }
    return names.get(ch)  # type: ignore[arg-type]


def layout(controller: Controller, width: int, height: int) -> dict:
    """Header, visible content and footer as plain data (also used by tests)."""
    screen = controller.screen
    lang = controller.language.upper()
    left = f" ◆ {screen.title()}" if len(controller.stack) == 1 and \
        screen.title() == controller.t("app.title") else f" ◆ AIO  ›  {screen.title()}"
    right = f" {lang} "
    header = Line([(pad(left, max(1, width - display_width(right))), "header"), (right, "badge")])
    footer: list = []
    for key, label in screen.hints():
        footer += [(f" {key} ", "key"), (f" {label} ", "dim")]
    return {"header": header, "lines": controller.render(width - 1),
            "status": controller.status, "footer": Line(footer, align=False)}


class CursesApp:
    def __init__(self, controller: Controller):
        self.c = controller
        self.scroll = 0
        self.last_focus: tuple | None = None
        self.last_view: tuple | None = None
        self.top = 2
        self.shown: list[Line] = []
        self.colors = False
        self.attrs: dict[str, int] = {}

    # -- colours --------------------------------------------------------------

    def init_colors(self) -> None:
        import curses

        self.attrs = {}
        many = False
        try:
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                many = curses.COLORS >= 256
                self.colors = True
        except curses.error:
            self.colors = False
        for pair, (name, (rich, basic, flags)) in enumerate(STYLES.items(), 1):
            value = 0
            if self.colors and name != "normal":
                if many:
                    fg, bg = rich
                else:
                    fg = getattr(curses, f"COLOR_{basic[0]}") if basic[0] else -1
                    bg = getattr(curses, f"COLOR_{basic[1]}") if basic[1] else -1
                try:
                    curses.init_pair(pair, fg, bg)
                    value = curses.color_pair(pair)
                except curses.error:
                    value = 0
            if not self.colors and name.startswith(("selected", "cursor", "header", "badge", "key")):
                value |= curses.A_REVERSE
            for flag in flags:
                if many and flag == "A_DIM":
                    continue  # the 256-colour grey is enough; A_DIM looks muddy there
                value |= getattr(curses, flag, 0)
            self.attrs[name] = value

    # -- drawing --------------------------------------------------------------

    def paint(self, win, y: int, item: Line, width: int) -> None:
        import curses

        x = 0
        used = item.width
        if self.c.rtl and item.align and used < width:
            x = width - used
        for text, style in item.parts:
            room = width - x
            if room <= 0:
                break
            text = clip(text, room)
            try:
                win.addstr(y, x, text, self.attrs.get(style, 0))
            except curses.error:  # writing the bottom-right cell raises; harmless
                pass
            x += display_width(text)
        if item.fill and x < width:
            try:
                win.addstr(y, x, " " * (width - x), self.attrs.get(item.fill, 0))
            except curses.error:
                pass

    def draw(self, win) -> None:
        import curses

        height, width = win.getmaxyx()
        view = (id(self.c.screen), self.c.language)
        if view != self.last_view:
            win.clear()  # full repaint when the screen or the language changes
            self.last_view = view
        else:
            win.erase()
        if height < 8 or width < 24:
            self.paint(win, 0, Line([(self.c.t("tui.too_small"), "warn")]), width)
            win.refresh()
            return
        data = layout(self.c, width, height)
        self.top = 2
        rows = height - self.top - 2
        lines = data["lines"]
        screen = self.c.screen
        focus = [i for i, item in enumerate(lines) if item.item == screen.selected]
        key = (id(screen), screen.selected, len(lines))
        if focus and key != self.last_focus:
            first, last = focus[0], focus[-1]
            if first < self.scroll:
                self.scroll = max(0, first - 1)
            elif last >= self.scroll + rows:
                self.scroll = min(first, last - rows + 2)
            self.last_focus = key
        if focus and focus[0] <= 4:
            self.scroll = 0  # keep the top of the screen (language box) visible
        self.scroll = max(0, min(self.scroll, max(0, len(lines) - rows)))
        self.shown = lines[self.scroll:self.scroll + rows]

        self.paint(win, 0, data["header"], width)
        cursor = None
        for y, item in enumerate(self.shown):
            self.paint(win, self.top + y, item, width - 1)
            if item.cursor is not None:
                cursor = (self.top + y, min(item.cursor, width - 2))
        if self.scroll > 0:
            self._corner(win, self.top, width, "▲")
        if self.scroll + rows < len(lines):
            self._corner(win, self.top + rows - 1, width, "▼")
        text, style = data["status"]
        if text:
            self.paint(win, height - 2, Line([(" " + text, style)]), width)
        self.paint(win, height - 1, data["footer"], width)
        try:
            if cursor:
                curses.curs_set(1)
                win.move(*cursor)
            else:
                curses.curs_set(0)
        except curses.error:
            pass
        win.refresh()

    def _corner(self, win, y: int, width: int, mark: str) -> None:
        import curses

        try:
            win.addstr(y, width - 1, mark, self.attrs.get("accent", 0))
        except curses.error:
            pass

    # -- input ----------------------------------------------------------------

    def tap(self, y: int, x: int, width: int) -> None:
        index = y - self.top
        if 0 <= index < len(self.shown) and self.shown[index].item is not None:
            self.c.tap(self.shown[index].item, x, width - 1)

    def run(self, win) -> None:
        import curses

        self.init_colors()
        try:
            curses.mousemask(curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED)
            curses.mouseinterval(0)
        except (curses.error, AttributeError):
            pass
        win.keypad(True)
        win.timeout(POLL_MS)
        dirty = True
        while self.c.running:
            if dirty:
                self.draw(win)
            try:
                ch = win.get_wch()
            except curses.error:  # timeout, no key
                dirty = False
                continue
            except KeyboardInterrupt:
                ch = "\x1b"
            key = key_name(ch)
            if key is None:
                continue
            dirty = True
            if key == "mouse":
                try:
                    _, x, y, _, state = curses.getmouse()
                except curses.error:
                    continue
                if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    self.tap(y, x, win.getmaxyx()[1])
            elif key == "resize":
                if hasattr(curses, "update_lines_cols"):
                    curses.update_lines_cols()
            else:
                self.c.handle(key)


def available(ctx: AppContext) -> bool:
    """Full-screen mode needs a real terminal, curses and no "simple" setting."""
    if os.environ.get("AIO_UI", "").lower() == "plain" or ctx.config.get("ui") == "plain":
        return False
    if os.environ.get("TERM", "dumb") in ("", "dumb"):
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import curses  # noqa: F401
    except ImportError:
        return False
    return True


def _startup_notice(ctx: AppContext, controller: Controller) -> None:
    """The quiet update check, with its message moved into the status line."""
    from aio.core.ui.update import check_on_start

    said: list[str] = []
    original = ctx.print_fn
    ctx.print_fn = lambda *args, **kwargs: said.append(" ".join(str(a) for a in args))
    try:
        check_on_start(ctx)
    finally:
        ctx.print_fn = original
    if said:
        controller.status = (said[-1].strip(), "warn")


def run(ctx: AppContext, first_start: bool = False, open_picker: bool = False) -> int:
    import curses

    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    os.environ.setdefault("ESCDELAY", "25")  # esc reacts at once instead of after 1 s
    controller = Controller(ctx, first_start=first_start, open_picker=open_picker)
    if not first_start:
        _startup_notice(ctx, controller)
    app = CursesApp(controller)
    while True:
        curses.wrapper(app.run)
        pending = controller.take_pending()
        if pending is None:
            break
        job, title = pending
        ctx.print_fn("")
        ctx.print_fn(f"\x1b[1;36m━━ {title} ━━\x1b[0m")
        try:
            job()
        except KeyboardInterrupt:
            ctx.print_fn("")
        ctx.print_fn("")
        ctx.ask(f"\x1b[2m{ctx.t('tui.press_enter')}\x1b[0m ")
    if controller.exit_code == 0:
        ctx.print_fn(ctx.t("app.goodbye"))
    return controller.exit_code
