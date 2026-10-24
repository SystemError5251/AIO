from aio.core import config
from aio.core.i18n import available_languages, get_translator
from aio.core.main import main
from aio.core.ui.language_picker import filter_languages


def test_first_start_shows_picker_and_saves_choice(term, monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    t = term(["", "q"])  # Enter = take suggested German, then quit
    assert main([], input_fn=t.input, print_fn=t.print, interactive=True) == 0
    assert "Wähle deine Sprache" in t.text
    assert "* 1) Deutsch" in t.text
    assert "Tschüss!" in t.text
    assert config.load()["language"] == "de"


def test_picker_search_then_number(term):
    t = term(["Engl", "1", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert config.load()["language"] == "en"


def test_picker_exact_code(term):
    t = term(["de", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert config.load()["language"] == "de"


def test_second_start_skips_picker(term):
    config.set_value("language", "de")
    t = term(["q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Wähle deine Sprache" not in t.text
    assert "Hallo (Demo)" in t.text


def test_choose_language_flag_shows_picker_again(term):
    config.set_value("language", "de")
    for flag in ("--lang", "--choose-language"):
        t = term(["en", "q"])
        main([flag], input_fn=t.input, print_fn=t.print, interactive=True)
        assert "Wähle deine Sprache" in t.text  # picker speaks the current language
        assert config.load()["language"] == "en"
        config.set_value("language", "de")


def test_lang_code_sets_directly(term):
    t = term([])
    assert main(["--lang", "de", "--list"], input_fn=t.input, print_fn=t.print) == 0
    assert "2 Tools verfügbar:" in t.text
    assert config.load()["language"] == "de"


def test_unknown_lang_code(term):
    t = term([])
    assert main(["--lang", "xx"], input_fn=t.input, print_fn=t.print) == 2


def test_abort_on_first_start_saves_nothing(term):
    t = term([])  # immediate EOF / Ctrl+D
    assert main([], input_fn=t.input, print_fn=t.print, interactive=True) == 1
    assert config.load()["language"] is None


def test_non_interactive_lists_tools_without_saving(term, monkeypatch):
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    t = term([])
    assert main([], input_fn=t.input, print_fn=t.print, interactive=False) == 0
    assert "Hallo (Demo)" in t.text
    assert config.load()["language"] is None


def test_change_language_in_settings(term):
    config.set_value("language", "de")
    t = term(["s", "1", "en", "b", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Language changed to English." in t.text
    assert config.load()["language"] == "en"
    get_translator().language = "en"


def test_run_dummy_tool(term):
    config.set_value("language", "en")
    t = term(["1", "", "JR", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert "Hello, JR!" in t.text
    assert "3 files" in t.text


def test_filter_matches_native_and_english_names():
    langs = available_languages()
    assert [l["code"] for l in filter_languages(langs, "deu")] == ["de"]
    assert [l["code"] for l in filter_languages(langs, "GERMAN")] == ["de"]
    assert len(filter_languages(langs, "")) == len(langs)
