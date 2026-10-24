"""Settings entry "Manage plugins": list, install and remove third-party tools."""

from __future__ import annotations

from aio.core import plugin_manager, registry
from aio.core.context import AppContext


def reload_plugins(ctx: AppContext) -> None:
    ctx.plugins = registry.discover()
    for plugin in ctx.plugins:
        ctx.translator.add_locales_dir(plugin.locales_dir)
    ctx.translator.reload()


def _install(ctx: AppContext) -> None:
    ctx.print(ctx.t("plugins.install_hint"))
    source = ctx.ask(ctx.t("plugins.install_prompt") + " ")
    if not source:
        return
    ctx.print(ctx.t("plugins.warning"))
    if not ctx.confirm(ctx.t("plugins.confirm_install")):
        return
    try:
        plugin = plugin_manager.install(source.strip("'\""))
    except plugin_manager.PluginError as exc:
        ctx.print(ctx.t(exc.key, **exc.kwargs))
        return
    reload_plugins(ctx)
    ctx.print(ctx.t("plugins.installed", name=ctx.t(plugin.name_key), version=plugin.version))


def _remove(ctx: AppContext) -> None:
    own = [p for p in ctx.plugins if not p.builtin]
    if not own:
        ctx.print(ctx.t("plugins.none_installed"))
        return
    for i, plugin in enumerate(own, 1):
        ctx.print(f"  {i:>2}) {ctx.t(plugin.name_key)} [{plugin.id}]")
    answer = ctx.ask(ctx.t("plugins.remove_prompt") + " ")
    if not answer or not answer.isdigit() or not 1 <= int(answer) <= len(own):
        return
    plugin = own[int(answer) - 1]
    if not ctx.confirm(ctx.t("plugins.confirm_remove", name=ctx.t(plugin.name_key))):
        return
    plugin_manager.remove(plugin.id)
    reload_plugins(ctx)
    ctx.print(ctx.t("plugins.removed", name=plugin.id))


def manage_plugins(ctx: AppContext) -> None:
    while True:
        ctx.print()
        ctx.print(f"== {ctx.t('settings.plugins')} ==")
        for plugin in ctx.plugins:
            origin = ctx.t("plugins.builtin" if plugin.builtin else "plugins.user")
            ctx.print(f"   - {ctx.t(plugin.name_key)} v{plugin.version} ({origin})")
        ctx.print(f"   i) {ctx.t('plugins.install')}")
        ctx.print(f"   r) {ctx.t('plugins.remove')}")
        ctx.print(f"   b) {ctx.t('menu.back')}")
        answer = ctx.ask(ctx.t("menu.prompt") + " ")
        if answer is None or answer.lower() in ("b", "q", ""):
            return
        if answer.lower() == "i":
            _install(ctx)
        elif answer.lower() == "r":
            _remove(ctx)
        else:
            ctx.print(ctx.t("menu.invalid"))
