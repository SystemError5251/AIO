"""Settings entries "Update now" and "Automatic updates", plus the check at start."""

from __future__ import annotations

import time

from aio.core import config, updater
from aio.core.context import AppContext


def _short(rev: str) -> str:
    return rev[:7]


def _install(ctx: AppContext, status: updater.UpdateStatus) -> bool:
    ctx.print(ctx.t("update.installing"))
    error = updater.install(status)
    if error:
        ctx.print(ctx.t(error))
        return False
    ctx.print(ctx.t("update.done", version=_short(status.remote)))
    return True


def update_now(ctx: AppContext) -> None:
    ctx.print(ctx.t("update.checking"))
    status = updater.check()
    ctx.config = config.set_value("update_last_check", int(time.time()))
    if status.error:
        ctx.print(ctx.t(status.error))
        return
    if not status.available:
        ctx.print(ctx.t("update.up_to_date", version=_short(status.local)))
        return
    ctx.print(ctx.t("update.available", old=_short(status.local),
                    new=_short(status.remote), subject=status.subject))
    if ctx.confirm(ctx.t("update.install_prompt")):
        _install(ctx, status)


def _mode_label(ctx: AppContext, mode: str) -> str:
    return ctx.t(f"update.mode_{mode}")


def _interval_label(ctx: AppContext, hours: int) -> str:
    return ctx.t(f"update.interval_{hours}")


def describe(ctx: AppContext) -> str:
    """Current automatic update setting, shown next to the menu entry."""
    mode, interval = updater.settings(ctx.config)
    if mode == "off":
        return _mode_label(ctx, mode)
    return f"{_mode_label(ctx, mode)}, {_interval_label(ctx, interval)}"


def _pick(ctx: AppContext, title: str, options: list[tuple[object, str]],
          current: object) -> object | None:
    ctx.print()
    ctx.print(f"== {title} ==")
    for i, (value, label) in enumerate(options, 1):
        mark = "*" if value == current else " "
        ctx.print(f" {mark} {i}) {label}")
    while True:
        answer = ctx.ask(ctx.t("menu.prompt") + " ")
        if not answer or answer.lower() in ("b", "q"):
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        ctx.print(ctx.t("menu.invalid"))


def auto_update_settings(ctx: AppContext) -> None:
    mode, interval = updater.settings(ctx.config)
    new_mode = _pick(ctx, ctx.t("update.auto_title"),
                     [(m, _mode_label(ctx, m)) for m in updater.MODES], mode)
    if new_mode is None:
        return
    ctx.config = config.set_value("update_mode", new_mode)
    if new_mode != "off":
        new_interval = _pick(ctx, ctx.t("update.interval_title"),
                             [(h, _interval_label(ctx, h)) for h in updater.INTERVALS],
                             interval)
        if new_interval is not None:
            ctx.config = config.set_value("update_interval_hours", new_interval)
    ctx.print(ctx.t("update.saved", setting=describe(ctx)))


def check_on_start(ctx: AppContext) -> None:
    """Quiet check before the main menu. Offline or failing = say nothing, start normally."""
    if not updater.is_due(ctx.config):
        return
    mode, _ = updater.settings(ctx.config)
    status = updater.check()
    ctx.config = config.set_value("update_last_check", int(time.time()))
    if status.error or not status.available:
        return
    if mode == "auto":
        if _install(ctx, status):
            return
    ctx.print(ctx.t("update.notice", new=_short(status.remote), subject=status.subject))
