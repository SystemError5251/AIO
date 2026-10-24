"""Merge reviewed translations (~/.aio/locales/<lang>.json) into the repository.

Someone checks texts in the app (Settings → Review translations) and shares the
file. This writes the corrections into the locale files and removes every
checked key from "_auto". Corrections with wrong placeholders are skipped.

    python -m aio.tools.merge_review ~/.aio/locales/fr.json
    python -m aio.tools.merge_review fr-review.json --lang fr
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aio.core.i18n import load_meta
from aio.core.review import merge_overlay
from aio.tools.translate import locale_dirs, read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--lang", help="language code (default: from the file name)")
    args = parser.parse_args(argv)
    meta = load_meta()
    status = 0
    for path in args.files:
        lang = args.lang or path.stem
        if lang not in meta:
            print(f"{path}: unknown language {lang!r}; use --lang", file=sys.stderr)
            status = 1
            continue
        changed, rejected = merge_overlay(locale_dirs(), lang, read(path))
        print(f"{path} -> {lang}: {changed} texts checked")
        for key in rejected:
            print(f"  skipped (placeholders do not match): {key}", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
