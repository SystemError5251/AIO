"""Report missing translation keys per language (core and every plugin).

German and English are required; a missing key there makes the check fail
(exit code 1). Other languages are only reported, since translate.py will
fill them later. A placeholder that the English text does not have also
fails the check, because it would be printed literally. Machine-translated
texts (listed under "_auto") are counted so they can be reviewed.

    python -m aio.tools.check_locales
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from aio.core.i18n import CORE_LOCALES_DIR
from aio.core.registry import BUILTIN_PLUGINS_DIR

REQUIRED = ("de", "en")
PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def _keys(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as fh:
        return {k for k in json.load(fh) if not k.startswith("_")}


def check_dir(locales_dir: Path, extra_keys: set[str] = frozenset()) -> dict[str, set[str]]:
    """Return {language: missing keys}; required languages are always checked."""
    files = {p.stem: p for p in locales_dir.glob("*.json") if not p.stem.startswith("_")}
    catalogs = {code: _keys(path) for code, path in files.items()}
    all_keys = set().union(*catalogs.values(), extra_keys) if catalogs else set(extra_keys)
    missing = {}
    for code in sorted(set(catalogs) | set(REQUIRED)):
        gap = all_keys - catalogs.get(code, set())
        if gap:
            missing[code] = gap
    return missing


def _placeholders(value) -> set[str]:
    texts = value.values() if isinstance(value, dict) else [value]
    return {p for t in texts for p in PLACEHOLDER.findall(str(t))}


def bad_placeholders(locales_dir: Path) -> dict[str, list[str]]:
    """{language: keys whose text uses a placeholder the English text lacks}."""
    en_path = locales_dir / "en.json"
    if not en_path.is_file():
        return {}
    with en_path.open(encoding="utf-8") as fh:
        en = json.load(fh)
    bad = {}
    for path in sorted(locales_dir.glob("*.json")):
        if path.stem.startswith("_") or path.stem == "en":
            continue
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        keys = [k for k, v in data.items() if not k.startswith("_") and k in en
                and _placeholders(v) - _placeholders(en[k])]
        if keys:
            bad[path.stem] = keys
    return bad


def auto_counts(locales_dir: Path) -> Counter:
    counts: Counter = Counter()
    for path in locales_dir.glob("*.json"):
        if not path.stem.startswith("_"):
            with path.open(encoding="utf-8") as fh:
                counts[path.stem] += len(json.load(fh).get("_auto", []))
    return counts


def main() -> int:
    failed = False
    targets = [("core", CORE_LOCALES_DIR, set())]
    for manifest in sorted(BUILTIN_PLUGINS_DIR.glob("*/manifest.json")):
        with manifest.open(encoding="utf-8") as fh:
            data = json.load(fh)
        declared = {data.get(k) for k in ("name_key", "desc_key", "help_key")} - {None}
        targets.append((f"plugin {manifest.parent.name}", manifest.parent / "locales", declared))
    auto: Counter = Counter()
    for label, directory, declared in targets:
        for code, keys in check_dir(directory, declared).items():
            required = code in REQUIRED
            failed |= required
            tag = "ERROR" if required else "missing"
            print(f"[{tag}] {label} / {code}: {', '.join(sorted(keys))}")
        for code, keys in bad_placeholders(directory).items():
            failed = True
            print(f"[ERROR] {label} / {code}: unknown placeholder in {', '.join(keys)}")
        auto += auto_counts(directory)
    if auto:
        print("Machine-translated, not yet reviewed: "
              + ", ".join(f"{code} {n}" for code, n in sorted(auto.items())))
    if not failed:
        print("OK: de and en are complete for core and all plugins.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
