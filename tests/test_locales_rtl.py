import json
from types import SimpleNamespace

import pytest

from aio.core import config
from aio.core.context import AppContext, align_rtl, display_width
from aio.core.i18n import Translator, available_languages, load_meta
from aio.core.main import main
from aio.tools import translate as tr

ALL_DIRS = tr.locale_dirs()
LANGS = sorted(load_meta())


def _load(path):
    return json.loads(path.read_text("utf-8"))


def test_every_meta_language_is_selectable():
    assert sorted(lang["code"] for lang in available_languages()) == LANGS
    assert len(LANGS) == 15


@pytest.mark.parametrize("lang", LANGS)
def test_language_is_complete_and_well_formed(lang):
    forms = tr.PLURAL_FORMS.get(lang, tr.DEFAULT_PLURAL_FORMS)
    for directory in ALL_DIRS:
        en = _load(directory / "en.json")
        data = _load(directory / f"{lang}.json")
        texts = {k: v for k, v in data.items() if not k.startswith("_")}
        assert set(texts) == {k for k in en if not k.startswith("_")}, directory
        assert set(data.get("_auto", [])) <= set(texts)
        for key, value in texts.items():
            assert tr.placeholders(value) <= tr.placeholders(en[key]), (lang, key)
            if isinstance(en[key], dict) and lang not in ("de", "en"):
                assert set(forms) <= set(value), (lang, key)
    core = _load(tr.CORE_LOCALES_DIR / f"{lang}.json")
    assert core["common.yes_letters"] and core["common.yes_no"]


def test_display_width():
    assert display_width("abc") == 3
    assert display_width("中文") == 4
    assert display_width("مرحبًا") == 5  # the tanwin mark takes no column


def test_align_rtl_right_aligns_and_wraps():
    out = align_rtl("سلام", 20).splitlines()
    assert out == [" " * 16 + "سلام"]
    long = align_rtl(" ".join(["كلمة"] * 20), 30).splitlines()
    assert len(long) > 1 and all(display_width(line) == 30 for line in long)


def test_rtl_flag_from_meta():
    assert Translator("ar").is_rtl and Translator("he").is_rtl
    assert not Translator("ja").is_rtl


def test_ctx_print_rtl(monkeypatch):
    lines = []
    ctx = AppContext(translator=Translator("he"), config={}, print_fn=lines.append)
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=None: SimpleNamespace(columns=20))
    ctx.print("שלום")
    assert lines == [" " * 16 + "שלום"]


def test_full_run_in_arabic(term):
    t = term(["ar", "q"])
    main([], input_fn=t.input, print_fn=t.print, interactive=True)
    assert config.load()["language"] == "ar"
    assert "إلى اللقاء!" in t.text
    title = next(line for line in t.lines if "الكل في واحد" in line)
    assert title.startswith(" ")


@pytest.mark.parametrize("lang, count, expected", [
    ("ru", 1, "Доступен 1 инструмент:"), ("ru", 3, "Доступно 3 инструмента:"),
    ("ru", 5, "Доступно 5 инструментов:"), ("pl", 22, "Dostępne 22 narzędzia:"),
    ("ja", 1, "利用できるツール：1 個"), ("ar", 2, "أداتان متاحتان:"),
])
def test_plural_forms_in_real_locales(lang, count, expected):
    assert Translator(lang).t("menu.tools", count=count) == expected


# --------------------------------------------------------------------------- #
# translate.py
# --------------------------------------------------------------------------- #

@pytest.fixture
def src(tmp_path):
    d = tmp_path / "locales"
    d.mkdir()
    (d / "en.json").write_text(json.dumps({
        "hello": "Hello {name}",
        "items": {"one": "{count} item", "other": "{count} items"},
    }), "utf-8")
    (d / "de.json").write_text(json.dumps({"hello": "Hallo {name}", "items": {"one": "{count} Ding", "other": "{count} Dinge"},
                                           "only.de": "Nur Deutsch"}), "utf-8")
    return d


def test_translate_dir_fills_marks_and_caches(src):
    calls = []

    def fetch(texts):
        calls.append(set(texts))
        return {"hello": "Привет {name}", "only.de": "Только немецкий",
                "items": {"one": "{count} штука", "other": "{count} штуки"}}

    cache = {}
    assert tr.translate_dir(src, "ru", cache, fetch) == 3
    data = _load(src / "ru.json")
    assert data["_auto"] == ["hello", "items", "only.de"]
    assert set(data["items"]) == {"one", "few", "many", "other"}  # missing forms fall back to "other"
    assert data["items"]["few"] == "{count} штуки"
    assert calls == [{"hello", "items", "only.de"}]

    (src / "ru.json").unlink()
    assert tr.translate_dir(src, "ru", cache, fetch) == 3
    assert len(calls) == 1  # second run served from the cache

    assert tr.translate_dir(src, "ru", cache, fetch) == 0  # nothing missing any more


def test_translate_keeps_reviewed_texts(src):
    (src / "fr.json").write_text(json.dumps({"hello": "Salut {name}"}), "utf-8")
    tr.translate_dir(src, "fr", {}, lambda texts: {"items": {"one": "{count} truc", "other": "{count} trucs"},
                                                    "only.de": "Seulement allemand"})
    data = _load(src / "fr.json")
    assert data["hello"] == "Salut {name}" and "hello" not in data["_auto"]


def test_validate_drops_invented_placeholders():
    good = tr.validate({"a": "Hi {name}", "b": "Bye"}, {"a": "Hola {nombre}", "b": "Adiós"}, "es")
    assert good == {"b": "Adiós"}
    with pytest.raises(ValueError):
        tr.validate({"a": "x"}, {"a": ""}, "es")
    with pytest.raises(ValueError):
        tr.validate({"a": "x"}, ["not", "a", "dict"], "es")


class FakeClient:
    def __init__(self, text, stop="end_turn"):
        self.kwargs = None
        self.reply = SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return self.reply


def test_call_claude_parses_json_and_sends_plural_forms():
    client = FakeClient('```json\n{"hello": "Hola {name}"}\n```')
    assert tr.call_claude(client, {"hello": "Hello {name}"}, "pl", "Polish") == {"hello": "Hola {name}"}
    assert client.kwargs["model"] == tr.MODEL
    assert "one, few, many, other" in client.kwargs["messages"][0]["content"]


def test_call_claude_refusal_and_cutoff():
    with pytest.raises(RuntimeError):
        tr.call_claude(FakeClient("", stop="refusal"), {"a": "b"}, "fr", "French")
    with pytest.raises(RuntimeError):
        tr.call_claude(FakeClient("{", stop="max_tokens"), {"a": "b"}, "fr", "French")


def test_dry_run_reports_complete(capsys):
    assert tr.main(["--dry-run", "fr", "ar"]) == 0
    assert capsys.readouterr().out.split() == ["fr:", "0", "missing", "ar:", "0", "missing"]


def test_unknown_language_is_rejected():
    assert tr.main(["--dry-run", "xx"]) == 2
