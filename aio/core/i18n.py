"""Translation layer: t("key"), fallback chain, plurals, RTL flag, formats.

Texts live in JSON files keyed by dotted names::

    {"menu.title": "Hauptmenü",
     "plugins.count": {"one": "{count} Tool", "other": "{count} Tools"}}

Lookup order is always: target language -> English -> the key itself, so the
screen is never empty. Keys starting with "_" are reserved for metadata.

`babel` is optional. When installed it provides CLDR plural rules and
locale-aware number/date formats; without it a small built-in rule set is used.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # pragma: no cover - depends on environment
    import babel  # type: ignore
    from babel import numbers as _babel_numbers  # type: ignore
    from babel import dates as _babel_dates  # type: ignore
except ImportError:  # pragma: no cover
    babel = None

FALLBACK_LANGUAGE = "en"
CORE_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


# --------------------------------------------------------------------------- #
# Language metadata
# --------------------------------------------------------------------------- #

def load_meta(locales_dir: Path = CORE_LOCALES_DIR) -> dict[str, dict[str, Any]]:
    """Read _meta.json: native name, English name and text direction per code."""
    try:
        with (locales_dir / "_meta.json").open(encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, json.JSONDecodeError):
        meta = {}
    return {code: info for code, info in meta.items() if not code.startswith("_")}


def available_languages(locales_dir: Path = CORE_LOCALES_DIR) -> list[dict[str, Any]]:
    """Languages that have a core locale file, enriched with _meta.json data.

    A new language only needs `<code>.json` (plus an entry in _meta.json for its
    native name); no code changes.
    """
    meta = load_meta(locales_dir)
    langs = []
    for path in sorted(locales_dir.glob("*.json")):
        code = path.stem
        if code.startswith("_"):
            continue
        info = meta.get(code, {})
        langs.append({
            "code": code,
            "name": info.get("name", code),
            "english_name": info.get("english_name", code),
            "dir": info.get("dir", "ltr"),
        })
    return langs


def normalize_code(value: str | None) -> str | None:
    """'de_DE.UTF-8' -> 'de', 'pt-BR' -> 'pt', 'C'/'POSIX' -> None."""
    if not value:
        return None
    value = value.split(":")[0]           # LANGUAGE may hold "de:en"
    value = value.split(".")[0].split("@")[0]
    value = value.replace("-", "_").split("_")[0].strip().lower()
    if not value or value in ("c", "posix"):
        return None
    return value


def detect_system_language(env: Mapping[str, str] | None = None,
                           available: list[str] | None = None) -> str:
    """Suggest a language from LC_ALL / LC_MESSAGES / LANG / LANGUAGE.

    Returns the first one that is available, else English.
    """
    env = os.environ if env is None else env
    if available is None:
        available = [lang["code"] for lang in available_languages()]
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        code = normalize_code(env.get(var))
        if code and code in available:
            return code
    return FALLBACK_LANGUAGE if FALLBACK_LANGUAGE in available or not available else available[0]


# --------------------------------------------------------------------------- #
# Plurals
# --------------------------------------------------------------------------- #

def _builtin_plural(lang: str, n: int) -> str:
    """Small subset of the CLDR rules for the planned start languages."""
    n = abs(int(n))
    if lang in ("zh", "ja", "ko", "vi", "th", "id"):
        return "other"
    if lang in ("fr", "hi", "pt"):
        return "one" if n in (0, 1) else "other"
    if lang in ("ru", "uk"):
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "pl":
        if n == 1:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if lang == "ar":
        if n == 0:
            return "zero"
        if n == 1:
            return "one"
        if n == 2:
            return "two"
        if 3 <= n % 100 <= 10:
            return "few"
        if 11 <= n % 100 <= 99:
            return "many"
        return "other"
    return "one" if n == 1 else "other"


def plural_category(lang: str, n: int) -> str:
    if babel is not None:
        try:
            return babel.Locale.parse(lang).plural_form(n)
        except Exception:  # unknown locale in babel -> built-in rules
            pass
    return _builtin_plural(lang, n)


# --------------------------------------------------------------------------- #
# Translator
# --------------------------------------------------------------------------- #

class _SafeDict(dict):
    """Leaves unknown {placeholders} untouched instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _read_catalog(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


class Translator:
    def __init__(self, language: str = FALLBACK_LANGUAGE,
                 locales_dir: Path = CORE_LOCALES_DIR) -> None:
        self.locales_dirs: list[Path] = [locales_dir]
        self.meta = load_meta(locales_dir)
        self._cache: dict[str, dict[str, Any]] = {}
        self.language = language

    # -- catalogs ---------------------------------------------------------- #

    def add_locales_dir(self, path: Path) -> None:
        """Register an extra locales folder (e.g. a plugin's own locales/)."""
        if path not in self.locales_dirs:
            self.locales_dirs.append(path)
            self._cache.clear()

    def _catalog(self, lang: str) -> dict[str, Any]:
        if lang not in self._cache:
            merged: dict[str, Any] = {}
            for directory in self.locales_dirs:
                merged.update(_read_catalog(directory / f"{lang}.json"))
            self._cache[lang] = merged
        return self._cache[lang]

    def has(self, key: str, lang: str | None = None) -> bool:
        return key in self._catalog(lang or self.language)

    # -- properties -------------------------------------------------------- #

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = normalize_code(value) or FALLBACK_LANGUAGE

    @property
    def is_rtl(self) -> bool:
        return self.meta.get(self.language, {}).get("dir") == "rtl"

    # -- lookup ------------------------------------------------------------ #

    def _lookup(self, key: str) -> tuple[Any, str] | None:
        for lang in dict.fromkeys((self.language, FALLBACK_LANGUAGE)):
            value = self._catalog(lang).get(key)
            if value is not None:
                return value, lang
        return None

    def t(self, key: str, count: int | None = None, **kwargs: Any) -> str:
        found = self._lookup(key)
        if found is None:
            return key
        value, lang = found
        if isinstance(value, dict):
            category = plural_category(lang, count if count is not None else 1)
            value = value.get(category) or value.get("other") or next(iter(value.values()), key)
        text = str(value)
        if count is not None:
            kwargs.setdefault("count", self.format_number(count))
        if kwargs:
            text = text.format_map(_SafeDict(kwargs))
        return text

    __call__ = t

    # -- formats ----------------------------------------------------------- #

    def format_number(self, value: float | int) -> str:
        if babel is not None:
            try:
                return _babel_numbers.format_decimal(value, locale=self.language)
            except Exception:
                pass
        return f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"

    def format_date(self, value: _dt.date | None = None) -> str:
        value = value or _dt.date.today()
        if babel is not None:
            try:
                return _babel_dates.format_date(value, format="medium", locale=self.language)
            except Exception:
                pass
        return value.isoformat()


# Process-wide translator so plugins can simply `from aio.core.i18n import t`.
_current = Translator()


def get_translator() -> Translator:
    return _current


def set_language(language: str) -> Translator:
    _current.language = language
    return _current


def t(key: str, count: int | None = None, **kwargs: Any) -> str:
    return _current.t(key, count=count, **kwargs)
