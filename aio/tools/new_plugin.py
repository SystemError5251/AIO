"""Create the skeleton of a new tool: manifest, plugin.py and de/en texts.

    python -m aio.tools.new_plugin my_tool              # in ~/.aio/plugins
    python -m aio.tools.new_plugin my_tool --dir aio/plugins
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aio.core import config, registry
from aio.core.plugin_manager import ID_PATTERN

PLUGIN_PY = '''"""{title}: describe what the tool does."""


def run(ctx):
    # ctx.t(key, **values) translates, ctx.print() prints (RTL-aware),
    # ctx.ask() / ctx.ask_file() / ctx.confirm() read input; None = cancelled.
    path = ctx.ask_file()
    if path is None:
        return
    ctx.print(ctx.t("{id}.done", path=str(path)))
'''

TEXTS = {
    "de": {"name": "{title}", "desc": "Kurzbeschreibung in einem Satz.",
           "help": "Ausführliche Hilfe: was das Tool macht, was es braucht.",
           "done": "Fertig: {{path}}"},
    "en": {"name": "{title}", "desc": "Short description in one sentence.",
           "help": "Detailed help: what the tool does and what it needs.",
           "done": "Done: {{path}}"},
}


def create(plugin_id: str, base: Path) -> Path:
    if not ID_PATTERN.match(plugin_id):
        raise ValueError("id must be lower case letters, digits and _ (e.g. my_tool)")
    folder = base / plugin_id
    if folder.exists():
        raise FileExistsError(folder)
    title = plugin_id.replace("_", " ").title()
    (folder / "locales").mkdir(parents=True)
    manifest = {"id": plugin_id, "version": "0.1.0", "api": registry.API_VERSION,
                "category": "misc", "requires": [],
                "name_key": f"{plugin_id}.name", "desc_key": f"{plugin_id}.desc",
                "help_key": f"{plugin_id}.help"}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    (folder / "plugin.py").write_text(PLUGIN_PY.format(title=title, id=plugin_id), "utf-8")
    for lang, texts in TEXTS.items():
        data = {f"{plugin_id}.{k}": v.format(title=title) for k, v in texts.items()}
        (folder / "locales" / f"{lang}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("id")
    parser.add_argument("--dir", type=Path, default=None,
                        help="parent folder (default: ~/.aio/plugins)")
    args = parser.parse_args(argv)
    try:
        folder = create(args.id, args.dir or config.user_plugins_dir())
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
