"""Loads and saves the user configuration in ~/.aio/config.json.

The base directory can be overridden with the AIO_HOME environment variable
(used by the tests and handy for portable setups).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "language": None,  # None = language has never been chosen
}


def aio_home() -> Path:
    override = os.environ.get("AIO_HOME")
    return Path(override).expanduser() if override else Path.home() / ".aio"


def config_path() -> Path:
    return aio_home() / "config.json"


def user_plugins_dir() -> Path:
    return aio_home() / "plugins"


def load() -> dict[str, Any]:
    """Return the config merged over DEFAULTS. A broken file never crashes the app."""
    data = dict(DEFAULTS)
    path = config_path()
    try:
        with path.open(encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            data.update(stored)
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        # Keep the defaults; the next save() rewrites a valid file.
        pass
    return data


def save(data: dict[str, Any]) -> None:
    """Write atomically so an interrupted write cannot corrupt the config."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def set_value(key: str, value: Any) -> dict[str, Any]:
    data = load()
    data[key] = value
    save(data)
    return data
