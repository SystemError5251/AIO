"""Install and remove third-party plugins in ~/.aio/plugins.

A source is a plugin folder, a .zip of one, or a git URL. The manifest must be
valid, the id may not clash with a built-in tool, and German and English texts
must be present (the rule every tool follows). Errors carry an i18n key.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from aio.core import config, registry

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
REQUIRED_LANGS = ("de", "en")


class PluginError(Exception):
    def __init__(self, key: str, **kwargs: str) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


def is_git_url(source: str) -> bool:
    return source.startswith(("https://", "git@")) and (
        source.endswith(".git") or "github.com/" in source or "gitlab.com/" in source)


def _extract_zip(path: Path, target: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                parts = PurePosixPath(name).parts
                if name.startswith("/") or ".." in parts:
                    raise PluginError("plugins.error_unsafe_zip")
            zf.extractall(target)
    except zipfile.BadZipFile as exc:
        raise PluginError("plugins.error_source", source=str(path)) from exc


def _clone(url: str, target: Path) -> None:
    if shutil.which("git") is None:
        raise PluginError("update.error_no_git")
    result = subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(target)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise PluginError("plugins.error_source", source=url)


def _find_plugin_folder(root: Path) -> Path:
    """The folder holding manifest.json: the root itself or its single subfolder."""
    if (root / "manifest.json").is_file():
        return root
    found = [p.parent for p in root.glob("*/manifest.json")]
    if len(found) == 1:
        return found[0]
    raise PluginError("plugins.error_no_manifest")


def inspect(folder: Path) -> registry.Plugin:
    try:
        plugin = registry._parse_manifest(folder)
    except (OSError, ValueError) as exc:
        raise PluginError("plugins.error_manifest", detail=str(exc)) from exc
    if not ID_PATTERN.match(plugin.id):
        raise PluginError("plugins.error_id", id=plugin.id)
    if (registry.BUILTIN_PLUGINS_DIR / plugin.id).exists():
        raise PluginError("plugins.error_builtin", id=plugin.id)
    missing = [lang for lang in REQUIRED_LANGS
               if not (plugin.locales_dir / f"{lang}.json").is_file()]
    if missing:
        raise PluginError("plugins.error_locales", langs=", ".join(missing))
    return plugin


def install(source: str) -> registry.Plugin:
    """Copy a plugin into ~/.aio/plugins/<id>; an older copy of the same id is replaced."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        path = Path(source).expanduser()
        if is_git_url(source):
            _clone(source, tmp_path / "src")
            root = tmp_path / "src"
        elif path.is_dir():
            root = path
        elif path.is_file() and path.suffix.lower() == ".zip":
            _extract_zip(path, tmp_path / "src")
            root = tmp_path / "src"
        else:
            raise PluginError("plugins.error_source", source=source)
        folder = _find_plugin_folder(root)
        plugin = inspect(folder)
        target = config.user_plugins_dir() / plugin.id
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(folder, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    return registry._parse_manifest(target)


def remove(plugin_id: str) -> None:
    target = config.user_plugins_dir() / plugin_id
    if not ID_PATTERN.match(plugin_id) or not (target / "manifest.json").is_file():
        raise PluginError("plugins.error_not_installed", id=plugin_id)
    shutil.rmtree(target)
