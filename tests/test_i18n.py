import json

import pytest

from aio.core import i18n
from aio.core.i18n import Translator, detect_system_language, normalize_code, plural_category


@pytest.fixture
def locales(tmp_path):
    d = tmp_path / "locales"
    d.mkdir()
    (d / "_meta.json").write_text(json.dumps({
        "en": {"name": "English", "english_name": "English", "dir": "ltr"},
        "fr": {"name": "Français", "english_name": "French", "dir": "ltr"},
        "ar": {"name": "العربية", "english_name": "Arabic", "dir": "rtl"},
    }), "utf-8")
    (d / "en.json").write_text(json.dumps({
        "hello": "Hello {name}",
        "only.en": "English only",
        "items": {"one": "{count} item", "other": "{count} items"},
    }), "utf-8")
    (d / "fr.json").write_text(json.dumps({"hello": "Bonjour {name}"}), "utf-8")
    (d / "ar.json").write_text("{}", "utf-8")
    return d


def test_fallback_chain_target_then_english_then_key(locales):
    tr = Translator("fr", locales_dir=locales)
    assert tr.t("hello", name="JR") == "Bonjour JR"
    assert tr.t("only.en") == "English only"
    assert tr.t("does.not.exist") == "does.not.exist"


def test_unknown_language_uses_english(locales):
    assert Translator("xx", locales_dir=locales).t("hello", name="A") == "Hello A"


def test_missing_placeholder_is_kept(locales):
    assert Translator("en", locales_dir=locales).t("hello") == "Hello {name}"


def test_plural(locales):
    tr = Translator("en", locales_dir=locales)
    assert tr.t("items", count=1) == "1 item"
    assert tr.t("items", count=5) == "5 items"


def test_rtl_flag(locales):
    assert Translator("ar", locales_dir=locales).is_rtl
    assert not Translator("fr", locales_dir=locales).is_rtl


def test_new_language_is_pure_data(locales):
    codes = [lang["code"] for lang in i18n.available_languages(locales)]
    assert codes == ["ar", "en", "fr"]
    (locales / "es.json").write_text("{}", "utf-8")  # no _meta entry yet
    langs = {lang["code"]: lang for lang in i18n.available_languages(locales)}
    assert langs["es"]["name"] == "es"


def test_plugin_locales_dir_is_merged(locales, tmp_path):
    plugin = tmp_path / "plugin_locales"
    plugin.mkdir()
    (plugin / "en.json").write_text(json.dumps({"tool.name": "Tool"}), "utf-8")
    tr = Translator("fr", locales_dir=locales)
    tr.add_locales_dir(plugin)
    assert tr.t("tool.name") == "Tool"


@pytest.mark.parametrize("value, expected", [
    ("de_DE.UTF-8", "de"), ("pt-BR", "pt"), ("en_US", "en"),
    ("C", None), ("POSIX", None), ("", None), (None, None), ("fr:en", "fr"),
])
def test_normalize_code(value, expected):
    assert normalize_code(value) == expected


def test_detect_system_language_order():
    avail = ["de", "en"]
    assert detect_system_language({"LANG": "de_DE.UTF-8"}, avail) == "de"
    assert detect_system_language({"LC_ALL": "en_GB.UTF-8", "LANG": "de_DE"}, avail) == "en"
    assert detect_system_language({"LC_ALL": "C", "LANG": "de_DE"}, avail) == "de"
    assert detect_system_language({"LANG": "ja_JP"}, avail) == "en"
    assert detect_system_language({}, avail) == "en"


@pytest.mark.parametrize("lang, n, expected", [
    ("de", 1, "one"), ("de", 0, "other"), ("fr", 0, "one"),
    ("ru", 1, "one"), ("ru", 3, "few"), ("ru", 11, "many"), ("ru", 21, "one"),
    ("pl", 22, "few"), ("pl", 5, "many"), ("ja", 1, "other"), ("ar", 2, "two"),
])
def test_builtin_plural_rules(lang, n, expected):
    assert i18n._builtin_plural(lang, n) == expected


def test_plural_category_returns_known_category():
    assert plural_category("de", 2) == "other"


def test_core_locales_de_en_have_same_keys():
    de = json.loads((i18n.CORE_LOCALES_DIR / "de.json").read_text("utf-8"))
    en = json.loads((i18n.CORE_LOCALES_DIR / "en.json").read_text("utf-8"))
    assert set(de) == set(en)
