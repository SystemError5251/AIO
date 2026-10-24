"""Updates AIO from GitHub, the same way aio-installer.sh does when it is rerun.

The installer clones AIO into ~/.aio/src (AIO_SRC overrides) and installs it
with pip. An update is: fetch the branch, reset the checkout to it, run pip
again. Every network step has a short timeout and never raises, so a phone
without network starts AIO as fast as always.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aio.core import config

MODES = ("off", "check", "auto")  # never / tell me / install by itself
INTERVALS = (0, 24, 168)  # hours between automatic checks: every start, daily, weekly
DEFAULT_MODE = "check"
DEFAULT_INTERVAL = 24
FETCH_TIMEOUT = 10  # seconds; keeps the start fast on a bad connection
PIP_TIMEOUT = 600

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass
class UpdateStatus:
    available: bool = False
    local: str = ""
    remote: str = ""
    subject: str = ""  # commit message of the new version
    error: str | None = None  # i18n key under "update.error_*"


def source_dir() -> Path:
    override = os.environ.get("AIO_SRC")
    return Path(override).expanduser() if override else config.aio_home() / "src"


def _git(src: Path, *args: str, run: Runner, timeout: float = FETCH_TIMEOUT) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # never wait for a password prompt
    result = run(["git", "-C", str(src), *args], capture_output=True, text=True,
                 timeout=timeout, env=env, check=True)
    return result.stdout.strip()


def check(src: Path | None = None, run: Runner = subprocess.run) -> UpdateStatus:
    """Fetch the branch and compare it with the installed checkout."""
    src = src or source_dir()
    if not (src / ".git").is_dir():
        return UpdateStatus(error="update.error_no_source")
    try:
        branch = _git(src, "rev-parse", "--abbrev-ref", "HEAD", run=run)
        if branch in ("", "HEAD"):
            branch = os.environ.get("AIO_BRANCH", "main")
        _git(src, "fetch", "--depth", "1", "origin", branch, run=run)
        local = _git(src, "rev-parse", "HEAD", run=run)
        remote = _git(src, "rev-parse", "FETCH_HEAD", run=run)
        subject = _git(src, "log", "-1", "--format=%s", "FETCH_HEAD", run=run)
    except FileNotFoundError:
        return UpdateStatus(error="update.error_no_git")
    except (subprocess.SubprocessError, OSError):
        return UpdateStatus(error="update.error_network")
    return UpdateStatus(available=local != remote, local=local, remote=remote, subject=subject)


def _pip_commands(src: Path) -> list[list[str]]:
    base = [sys.executable, "-m", "pip", "install", "--upgrade", str(src)]
    in_venv = sys.prefix != sys.base_prefix
    if in_venv or os.environ.get("TERMUX_VERSION"):
        return [base]
    # Same order as aio-installer.sh on Linux.
    return [base[:4] + ["--user"] + base[4:],
            base[:4] + ["--user", "--break-system-packages"] + base[4:]]


def install(status: UpdateStatus, src: Path | None = None,
            run: Runner = subprocess.run,
            pip_commands: Sequence[Sequence[str]] | None = None) -> str | None:
    """Move the checkout to the fetched version and reinstall. Returns an error key or None."""
    src = src or source_dir()
    try:
        _git(src, "reset", "--hard", status.remote, run=run)
    except FileNotFoundError:
        return "update.error_no_git"
    except (subprocess.SubprocessError, OSError):
        return "update.error_install"
    for cmd in (_pip_commands(src) if pip_commands is None else pip_commands):
        try:
            run(list(cmd), capture_output=True, text=True, timeout=PIP_TIMEOUT, check=True)
            return None
        except (subprocess.SubprocessError, OSError):
            continue
    return "update.error_install"


def settings(cfg: dict[str, Any]) -> tuple[str, int]:
    mode = cfg.get("update_mode", DEFAULT_MODE)
    interval = cfg.get("update_interval_hours", DEFAULT_INTERVAL)
    return (mode if mode in MODES else DEFAULT_MODE,
            interval if interval in INTERVALS else DEFAULT_INTERVAL)


def is_due(cfg: dict[str, Any], now: float | None = None) -> bool:
    mode, interval = settings(cfg)
    if mode == "off":
        return False
    last = cfg.get("update_last_check") or 0
    now = time.time() if now is None else now
    return not isinstance(last, (int, float)) or now - last >= interval * 3600
