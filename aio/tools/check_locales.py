"""Report missing translation keys per language (core and every plugin).

German and English are required; a missing key there makes the check fail
(exit code 1). Other languages are only reported, since translate.py will
fill them later.

    python -m aio.tools.check_locales
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from aio.core.i18n import CORE_LOCALES_DIR
from aio.core.registry import BUILTIN_PLUGINS_DIR

REQUIRED = ("de", "en")


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


def main() -> int:
    failed = False
    targets = [("core", CORE_LOCALES_DIR, set())]
    for manifest in sorted(BUILTIN_PLUGINS_DIR.glob("*/manifest.json")):
        with manifest.open(encoding="utf-8") as fh:
            data = json.load(fh)
        declared = {data.get(k) for k in ("name_key", "desc_key", "help_key")} - {None}
        targets.append((f"plugin {manifest.parent.name}", manifest.parent / "locales", declared))
    for label, directory, declared in targets:
        for code, keys in check_dir(directory, declared).items():
            required = code in REQUIRED
            failed |= required
            tag = "ERROR" if required else "missing"
            print(f"[{tag}] {label} / {code}: {', '.join(sorted(keys))}")
    if not failed:
        print("OK: de and en are complete for core and all plugins.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
