"""Main menu: tool list with short descriptions, tool help, settings."""

from __future__ import annotations

from aio.core import config
from aio.core.context import AppContext
from aio.core.i18n import load_meta
from aio.core.media import MissingTool
from aio.core.registry import Plugin
from aio.core.ui.doctor import system_check
from aio.core.ui.language_picker import choose_language
from aio.core.ui.plugins import manage_plugins
from aio.core.ui.review import open_count, review_translations
from aio.core.ui.update import auto_update_settings, describe, update_now


def change_language(ctx: AppContext) -> None:
    code = choose_language(ctx, current=ctx.translator.language)
    if code and code != ctx.translator.language:
        ctx.translator.language = code
        ctx.config = config.set_value("language", code)
        ctx.print(ctx.t("settings.language_changed", language=_language_name(code)))


def _language_name(code: str) -> str:
    return load_meta().get(code, {}).get("name", code)


def print_tool_list(ctx: AppContext) -> None:
    ctx.print(ctx.t("menu.tools", count=len(ctx.plugins)))
    if not ctx.plugins:
        ctx.print("  " + ctx.t("menu.no_tools"))
    for i, plugin in enumerate(ctx.plugins, 1):
        ctx.print(f"  {i:>2}) {ctx.t(plugin.name_key)}")
        ctx.print(f"      {ctx.t(plugin.desc_key)}")


def show_tool(ctx: AppContext, plugin: Plugin) -> None:
    ctx.print()
    ctx.print(f"== {ctx.t(plugin.name_key)} (v{plugin.version}) ==")
    ctx.print(ctx.t(plugin.help_key))
    ctx.print()
    answer = ctx.ask(ctx.t("tool.start_prompt") + " ")
    if answer is None or answer.lower() in ("b", "q"):
        return
    try:
        plugin.run(ctx)
    except MissingTool as exc:
        ctx.print(ctx.t("tool.missing_program", name=exc.name, package=exc.package))
    except Exception as exc:  # a broken tool must not crash the whole app
        ctx.print(ctx.t("tool.error", error=f"{type(exc).__name__}: {exc}"))


def settings_menu(ctx: AppContext) -> None:
    while True:
        ctx.print()
        ctx.print(f"== {ctx.t('settings.title')} ==")
        ctx.print(f"   1) {ctx.t('settings.language')} "
                  f"({_language_name(ctx.translator.language)})")
        ctx.print(f"   2) {ctx.t('settings.display_help')}")
        ctx.print(f"   3) {ctx.t('settings.update_now')}")
        ctx.print(f"   4) {ctx.t('settings.auto_update')} ({describe(ctx)})")
        pending = open_count(ctx)
        ctx.print(f"   5) {ctx.t('settings.review')}"
                  + (f" ({pending})" if pending else ""))
        ctx.print(f"   6) {ctx.t('settings.plugins')} ({len(ctx.plugins)})")
        ctx.print(f"   7) {ctx.t('settings.doctor')}")
        ctx.print(f"   b) {ctx.t('menu.back')}")
        answer = ctx.ask(ctx.t("menu.prompt") + " ")
        if answer is None or answer.lower() in ("b", "q", ""):
            return
        if answer == "1":
            change_language(ctx)
        elif answer == "2":
            ctx.print(ctx.t("help.display"))
        elif answer == "3":
            update_now(ctx)
        elif answer == "4":
            auto_update_settings(ctx)
        elif answer == "5":
            review_translations(ctx)
        elif answer == "6":
            manage_plugins(ctx)
        elif answer == "7":
            system_check(ctx)
        else:
            ctx.print(ctx.t("menu.invalid"))


def main_menu(ctx: AppContext) -> None:
    while True:
        ctx.print()
        ctx.print(f"== {ctx.t('app.title')} ==")
        print_tool_list(ctx)
        ctx.print()
        ctx.print(f"   s) {ctx.t('menu.settings')}")
        ctx.print(f"   q) {ctx.t('menu.quit')}")
        answer = ctx.ask(ctx.t("menu.prompt") + " ")
        if answer is None or answer.lower() == "q":
            ctx.print(ctx.t("app.goodbye"))
            return
        if answer.lower() == "s":
            settings_menu(ctx)
        elif answer.isdigit() and 1 <= int(answer) <= len(ctx.plugins):
            show_tool(ctx, ctx.plugins[int(answer) - 1])
        elif answer:
            ctx.print(ctx.t("menu.invalid"))
