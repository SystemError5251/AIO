"""Fill missing translations with the Claude API.

Only keys that are missing in a target language are sent; English is the
source (German where English lacks a key). Results are cached in
~/.aio/translate_cache.json, so the same text is never paid for twice, and
every machine-translated key is listed under "_auto" in the target file so
a human can review it. Remove a key from "_auto" once it has been checked.

    pip install -e ".[translate]"
    export ANTHROPIC_API_KEY=...
    python -m aio.tools.translate              # all languages from _meta.json
    python -m aio.tools.translate fr es        # only these
    python -m aio.tools.translate --dry-run    # just count what is missing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aio.core import config
from aio.core.i18n import CORE_LOCALES_DIR, load_meta
from aio.core.registry import BUILTIN_PLUGINS_DIR

MODEL = "claude-opus-5-5"
SOURCE_LANGS = ("en", "de")
AUTO_KEY = "_auto"
PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")

# CLDR plural categories the translation must provide, per language.
PLURAL_FORMS = {
    "zh": ["other"], "ja": ["other"], "ko": ["other"], "vi": ["other"], "th": ["other"], "id": ["other"],
    "ru": ["one", "few", "many", "other"], "uk": ["one", "few", "many", "other"],
    "pl": ["one", "few", "many", "other"],
    "ar": ["zero", "one", "two", "few", "many", "other"],
}
DEFAULT_PLURAL_FORMS = ["one", "other"]

SYSTEM = (
    "You translate user interface texts of a command line toolkit for Android/Termux. "
    "Return only a JSON object with exactly the same keys as the input. Keep every "
    "{placeholder} unchanged, keep program names, commands, file paths and file "
    "extensions as they are, and keep texts short and natural for a phone screen. "
    "A value that is an object holds plural forms: return an object with exactly the "
    "plural categories requested for the target language."
)


def locale_dirs() -> list[Path]:
    dirs = [CORE_LOCALES_DIR]
    dirs += sorted(p.parent for p in BUILTIN_PLUGINS_DIR.glob("*/locales/en.json"))
    return dirs


def read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_texts(directory: Path) -> dict[str, Any]:
    """English texts, with German filling any key English lacks."""
    merged: dict[str, Any] = {}
    for lang in reversed(SOURCE_LANGS):
        merged.update({k: v for k, v in read(directory / f"{lang}.json").items()
                       if not k.startswith("_")})
    order = [k for k in read(directory / "en.json") if not k.startswith("_")]
    return {k: merged[k] for k in order + [k for k in merged if k not in order]}


def missing(directory: Path, lang: str) -> dict[str, Any]:
    target = read(directory / f"{lang}.json")
    return {k: v for k, v in source_texts(directory).items() if k not in target}


def placeholders(value: Any) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return {p for t in texts for p in PLACEHOLDER.findall(str(t))}


def validate(source: dict[str, Any], result: Any, lang: str) -> dict[str, Any]:
    """Keep only well-formed translations; raise if nothing usable came back."""
    if not isinstance(result, dict):
        raise ValueError("response is not a JSON object")
    forms = PLURAL_FORMS.get(lang, DEFAULT_PLURAL_FORMS)
    good = {}
    for key, value in source.items():
        out = result.get(key)
        if isinstance(value, dict):
            if not isinstance(out, dict) or "other" not in out:
                continue
            out = {f: str(out.get(f) or out["other"]) for f in forms}
        elif not isinstance(out, str) or not out.strip():
            continue
        if placeholders(out) - placeholders(value):
            continue  # invented placeholder would print literally
        good[key] = out
    if source and not good:
        raise ValueError("no valid translations in response")
    return good


def _cache_key(lang: str, key: str, value: Any) -> str:
    raw = json.dumps([lang, key, value], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache() -> dict[str, Any]:
    return read(config.aio_home() / "translate_cache.json")


def save_cache(cache: dict[str, Any]) -> None:
    path = config.aio_home() / "translate_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path, cache)


def call_claude(client: Any, texts: dict[str, Any], lang: str, lang_name: str,
                model: str = MODEL) -> dict[str, Any]:
    forms = PLURAL_FORMS.get(lang, DEFAULT_PLURAL_FORMS)
    prompt = (f"Target language: {lang_name} ({lang}). "
              f"Plural categories for this language: {', '.join(forms)}.\n\n"
              + json.dumps(texts, ensure_ascii=False, indent=2))
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("the request was declined")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("response was cut off; translate fewer keys at once")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def translate_dir(directory: Path, lang: str, cache: dict[str, Any],
                  fetch: Callable[[dict[str, Any]], Any]) -> int:
    """Add missing texts to <directory>/<lang>.json; `fetch` translates a {key: text} batch."""
    todo = missing(directory, lang)
    if not todo:
        return 0
    done: dict[str, Any] = {}
    uncached = {}
    for key, value in todo.items():
        hit = cache.get(_cache_key(lang, key, value))
        if hit is not None:
            done[key] = hit
        else:
            uncached[key] = value
    if uncached:
        fresh = validate(uncached, fetch(uncached), lang)
        for key, value in fresh.items():
            cache[_cache_key(lang, key, uncached[key])] = value
        done.update(fresh)

    path = directory / f"{lang}.json"
    target = read(path)
    auto = set(target.get(AUTO_KEY, [])) | set(done)
    target.update(done)
    order = list(source_texts(directory))
    merged = {AUTO_KEY: sorted(auto)} if auto else {}
    merged.update({k: target[k] for k in order if k in target})
    merged.update({k: v for k, v in target.items() if k not in merged and k != AUTO_KEY})
    write(path, merged)
    return len(done)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="translate", description=__doc__.splitlines()[0])
    parser.add_argument("langs", nargs="*", help="language codes (default: all in _meta.json)")
    parser.add_argument("--dry-run", action="store_true", help="only report missing keys")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)

    meta = load_meta()
    langs = args.langs or [c for c in meta if c not in SOURCE_LANGS]
    unknown = [c for c in langs if c not in meta]
    if unknown:
        print(f"Add these to aio/locales/_meta.json first: {', '.join(unknown)}", file=sys.stderr)
        return 2

    if args.dry_run:
        for lang in langs:
            count = sum(len(missing(d, lang)) for d in locale_dirs())
            print(f"{lang}: {count} missing")
        return 0

    try:
        import anthropic
    except ImportError:
        print('Install the SDK first: pip install -e ".[translate]"', file=sys.stderr)
        return 2
    client = anthropic.Anthropic()
    cache = load_cache()
    failed = False
    try:
        for lang in langs:
            name = meta[lang].get("english_name", lang)
            total = 0
            for directory in locale_dirs():
                try:
                    total += translate_dir(directory, lang, cache, lambda texts: call_claude(
                        client, texts, lang, name, args.model))
                except anthropic.AuthenticationError:
                    raise
                except (anthropic.APIError, RuntimeError, ValueError) as exc:
                    failed = True
                    print(f"{lang} / {directory.parent.name}: {exc}", file=sys.stderr)
                finally:
                    save_cache(cache)
            print(f"{lang}: {total} texts added")
    except anthropic.AuthenticationError:
        print("No valid API key: set ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
