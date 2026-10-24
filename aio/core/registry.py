"""Discovers plugins automatically from folders containing a manifest.json.

Search paths: the built-in aio/plugins/ and the user's ~/.aio/plugins/.
A plugin folder looks like::

    my_tool/
      manifest.json   # id, version, name_key, desc_key, help_key, ...
      plugin.py       # defines run(ctx)
      locales/de.json en.json ...

Broken plugins are skipped with a warning instead of taking the app down.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from aio.core import config

BUILTIN_PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
REQUIRED_FIELDS = ("id", "version", "name_key", "desc_key", "help_key")
# Version of the plugin interface (run(ctx), AppContext, aio.core.media). A plugin
# may declare "api": N in its manifest; one newer than this AIO is skipped.
API_VERSION = 1


@dataclass
class Plugin:
    id: str
    version: str
    name_key: str
    desc_key: str
    help_key: str
    path: Path
    entry: str = "plugin.py"
    category: str = "misc"
    requires: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)
    _module: ModuleType | None = field(default=None, repr=False)

    @property
    def builtin(self) -> bool:
        return self.path.parent == BUILTIN_PLUGINS_DIR

    @property
    def locales_dir(self) -> Path:
        return self.path / "locales"

    def load(self) -> ModuleType:
        """Import plugin.py lazily, only when the tool is actually opened."""
        if self._module is None:
            entry = self.path / self.entry
            name = f"aio_plugin_{self.id}"
            spec = importlib.util.spec_from_file_location(name, entry)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {entry}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            self._module = module
        return self._module

    def run(self, ctx: Any) -> Any:
        module = self.load()
        run = getattr(module, "run", None)
        if not callable(run):
            raise AttributeError(f"plugin {self.id!r} has no run(ctx) function")
        return run(ctx)


def _parse_manifest(folder: Path) -> Plugin:
    with (folder / "manifest.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    api = data.get("api", 1)
    if not isinstance(api, int) or api > API_VERSION:
        raise ValueError(f"needs plugin API {api}, this AIO has {API_VERSION}; update AIO")
    entry = data.get("entry", "plugin.py")
    if not (folder / entry).is_file():
        raise ValueError(f"entry file {entry!r} not found")
    return Plugin(
        id=data["id"],
        version=str(data["version"]),
        name_key=data["name_key"],
        desc_key=data["desc_key"],
        help_key=data["help_key"],
        path=folder,
        entry=entry,
        category=data.get("category", "misc"),
        requires=list(data.get("requires", [])),
        manifest=data,
    )


def default_search_paths() -> list[Path]:
    return [BUILTIN_PLUGINS_DIR, config.user_plugins_dir()]


def discover(search_paths: list[Path] | None = None,
             warnings: list[str] | None = None) -> list[Plugin]:
    """Return all valid plugins, sorted by id. Later paths cannot shadow ids."""
    plugins: dict[str, Plugin] = {}
    for base in search_paths if search_paths is not None else default_search_paths():
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            if not (folder / "manifest.json").is_file():
                continue
            try:
                plugin = _parse_manifest(folder)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                if warnings is not None:
                    warnings.append(f"{folder.name}: {exc}")
                continue
            if plugin.id in plugins:
                if warnings is not None:
                    warnings.append(f"{folder}: duplicate plugin id {plugin.id!r}")
                continue
            plugins[plugin.id] = plugin
    return sorted(plugins.values(), key=lambda p: p.id)
