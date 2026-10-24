"""Entry point `aio`: language selection screen -> main UI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from aio import __version__
from aio.core import config, registry, review
from aio.core.context import AppContext
from aio.core.i18n import available_languages, detect_system_language, get_translator
from aio.core.ui.language_picker import choose_language
from aio.core.ui.menu import main_menu, print_tool_list
from aio.core.ui.review import review_translations
from aio.core.ui.update import check_on_start, update_now

CHOOSE = "__choose__"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aio", description="AIO – All-in-One toolkit")
    parser.add_argument(
        "--lang", nargs="?", const=CHOOSE, metavar="CODE",
        help="show the language selection again, or set a language directly (e.g. --lang de)",
    )
    parser.add_argument(
        "--choose-language", dest="lang", action="store_const", const=CHOOSE,
        help="show the language selection again",
    )
    parser.add_argument("--review", action="store_true",
                        help="review machine-translated texts of the current language and exit")
    parser.add_argument("--update", action="store_true", help="update AIO from GitHub and exit")
    parser.add_argument("--list", action="store_true", help="list tools and exit")
    parser.add_argument("--version", action="version", version=f"aio {__version__}")
    return parser


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: Sequence[str] | None = None,
         input_fn: Callable[[str], str] = input,
         print_fn: Callable[..., None] = print,
         interactive: bool | None = None) -> int:
    _force_utf8()
    args = build_parser().parse_args(argv)
    if interactive is None:
        interactive = sys.stdin.isatty()

    cfg = config.load()
    codes = [lang["code"] for lang in available_languages()]
    translator = get_translator()
    saved = cfg.get("language") if cfg.get("language") in codes else None
    translator.language = saved or detect_system_language(available=codes)

    warnings: list[str] = []
    plugins = registry.discover(warnings=warnings)
    for plugin in plugins:
        translator.add_locales_dir(plugin.locales_dir)
    translator.set_override_dir(review.user_locales_dir())

    ctx = AppContext(translator=translator, config=cfg, plugins=plugins,
                     input_fn=input_fn, print_fn=print_fn)
    for warning in warnings:
        print_fn(ctx.t("registry.plugin_skipped", detail=warning), file=sys.stderr)

    # --lang CODE: set directly, no picker.
    if args.lang and args.lang != CHOOSE:
        code = args.lang.lower()
        if code not in codes:
            print_fn(ctx.t("cli.unknown_language", code=code, available=", ".join(codes)),
                     file=sys.stderr)
            return 2
        translator.language = code
        ctx.config = config.set_value("language", code)
        saved = code

    # Language selection BEFORE the UI: first start, or --lang / --choose-language.
    if args.lang == CHOOSE or saved is None:
        if interactive:
            code = choose_language(ctx, current=saved)
            if code is None:
                if saved is None:
                    return 1  # aborted on first start: nothing chosen, nothing saved
            else:
                translator.language = code
                ctx.config = config.set_value("language", code)
        # Non-interactive (pipes, scripts): use the suggestion without saving it.

    if args.update:
        update_now(ctx)
        return 0

    if args.review:
        if not interactive:
            return 2
        review_translations(ctx)
        return 0

    if args.list or not interactive:
        print_tool_list(ctx)
        return 0

    check_on_start(ctx)
    main_menu(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
