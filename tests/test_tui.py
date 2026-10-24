from aio.core import config, registry
from aio.core.context import AppContext, display_width
from aio.core.i18n import get_translator
from aio.core.main import main
from aio.core.tui import app as tui_app
from aio.core.tui.screens import Controller, HomeScreen, LanguageScreen, SettingsScreen, ToolScreen
from aio.core.tui.widgets import clip, wrap


def make(first_start=False, open_picker=False, language="de"):
    translator = get_translator()
    translator.language = language
    plugins = registry.discover()
    for plugin in plugins:
        translator.add_locales_dir(plugin.locales_dir)
    ctx = AppContext(translator=translator, config=config.load(), plugins=plugins)
    return Controller(ctx, first_start=first_start, open_picker=open_picker)


def text(c, width=60):
    return "\n".join(line.text for line in c.render(width))


def press(c, *keys):
    for key in keys:
        c.handle(key)


def test_home_starts_on_the_language_box():
    c = make()
    assert isinstance(c.screen, HomeScreen)
    assert c.screen.selected == 0
    shown = text(c)
    assert "Sprache · Language" in shown
    assert "◀   Deutsch  (German)   ▶" in shown
    assert "VIDEO" in shown and "Einstellungen" in shown


def test_arrows_switch_language_at_once_and_save_it():
    c = make()
    press(c, "right")
    assert c.language == "en"
    assert config.load()["language"] == "en"
    assert "Language changed to English." in c.status[0]
    assert "◀   English   ▶" in text(c)
    press(c, "left", "left")
    assert c.language == available_codes()[available_codes().index("de") - 1]
    get_translator().language = "en"


def available_codes():
    from aio.core.i18n import available_languages
    return [lang["code"] for lang in available_languages()]


def test_tap_on_language_box_sides():
    c = make()
    c.tap(0, 2, 60)  # left third
    assert c.language != "de"
    c.tap(0, 30, 60)  # middle opens the full list
    assert isinstance(c.screen, LanguageScreen)
    get_translator().language = "en"


def test_language_screen_search_and_choose():
    c = make()
    press(c, "enter")
    assert isinstance(c.screen, LanguageScreen)
    press(c, *"japa")
    shown = text(c)
    assert "日本語" in shown and "Deutsch" not in shown
    press(c, "enter")
    assert isinstance(c.screen, HomeScreen)
    assert config.load()["language"] == "ja"
    get_translator().language = "en"


def test_language_screen_escape_clears_search_then_leaves():
    c = make()
    press(c, "l", "x", "x", "x")
    assert "Keine Sprache passt." in text(c) or "passt" in text(c)
    press(c, "back")
    assert c.screen.query == ""
    press(c, "back")
    assert isinstance(c.screen, HomeScreen)


def test_first_start_shows_language_list_and_abort_saves_nothing():
    c = make(first_start=True, language="en")
    assert isinstance(c.screen, LanguageScreen)
    press(c, "back")
    assert not c.running and c.exit_code == 1
    assert config.load()["language"] is None


def test_first_start_choice_leads_to_home():
    c = make(first_start=True, language="en")
    press(c, *"deu", "enter")
    assert isinstance(c.screen, HomeScreen) and len(c.stack) == 1
    assert config.load()["language"] == "de"
    get_translator().language = "en"


def test_open_picker_flag():
    c = make(open_picker=True)
    assert isinstance(c.screen, LanguageScreen) and len(c.stack) == 2


def test_tool_screen_and_external_run():
    c = make(language="en")
    press(c, "1")
    assert isinstance(c.screen, ToolScreen)
    shown = text(c)
    assert "About this tool" in shown and "Start tool" in shown
    press(c, "enter")
    assert not c.running
    job, title = c.take_pending()
    assert c.running and title == c.screen.title()


def test_settings_toggle_ui_and_back():
    c = make(language="en")
    press(c, "s")
    assert isinstance(c.screen, SettingsScreen)
    press(c, "down", "right")
    assert config.load()["ui"] == "plain"
    press(c, "q")
    assert isinstance(c.screen, HomeScreen)


def test_escape_on_home_does_not_quit_but_q_does():
    c = make()
    press(c, "back")
    assert c.running
    press(c, "q")
    assert not c.running and c.exit_code == 0


def test_every_language_renders_on_a_small_screen():
    c = make()
    for code in available_codes():
        c.set_language(code)
        for screen in (HomeScreen(c), SettingsScreen(c), LanguageScreen(c)):
            c.stack = [screen]
            for item in c.render(39):
                assert display_width(item.text) <= 39, (code, item.text)
            data = tui_app.layout(c, 40, 20)
            assert data["header"].width <= 40
    get_translator().language = "en"


def test_clip_and_wrap_count_wide_characters():
    assert clip("中文中文中文", 5) == "中文…"
    assert all(display_width(part) <= 6 for part in wrap("日本語のテキストです", 6))
    assert wrap("a b\n\n  c", 10) == ["a b", "", "  c"]


def test_main_uses_plain_ui_for_scripts(term, monkeypatch):
    called = []
    monkeypatch.setattr("aio.core.main.run_tui", lambda *a, **k: called.append(1) or 0)
    t = term(["q"])
    config.set_value("language", "en")
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert not called  # a scripted input_fn always gets the text UI


def test_main_picks_full_screen_on_a_terminal(monkeypatch):
    seen = {}
    monkeypatch.setattr("aio.core.main.tui_available", lambda ctx: True)
    monkeypatch.setattr("aio.core.main.run_tui",
                        lambda ctx, first_start, open_picker: seen.update(
                            first=first_start, picker=open_picker) or 0)
    assert main([], interactive=True) == 0
    assert seen == {"first": True, "picker": False}
    config.set_value("language", "de")
    assert main(["--lang"], interactive=True) == 0
    assert seen == {"first": False, "picker": True}
    seen.clear()
    main(["--plain", "--list"], interactive=True)
    assert not seen
    get_translator().language = "en"


def test_available_respects_plain_setting(monkeypatch):
    c = make()
    monkeypatch.setenv("AIO_UI", "plain")
    assert not tui_app.available(c.ctx)
