"""Language selection screen, shown before the main UI.

Each language is listed in its own script (Deutsch, English, العربية, 中文 ...).
Typing text filters the list; a number or an exact code/name picks a language;
Enter accepts the suggested one (system language from LANG/LC_ALL).
"""

from __future__ import annotations

from typing import Any

from aio.core.context import AppContext
from aio.core.i18n import available_languages, detect_system_language


def filter_languages(langs: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Case-insensitive match against code, native name and English name."""
    q = query.strip().casefold()
    if not q:
        return list(langs)
    return [
        lang for lang in langs
        if q in lang["code"].casefold()
        or q in lang["name"].casefold()
        or q in lang["english_name"].casefold()
    ]


def _exact_match(langs: list[dict[str, Any]], answer: str) -> dict[str, Any] | None:
    a = answer.casefold()
    for lang in langs:
        if a in (lang["code"].casefold(), lang["name"].casefold(), lang["english_name"].casefold()):
            return lang
    return None


def choose_language(ctx: AppContext, current: str | None = None) -> str | None:
    """Run the picker. Returns the chosen code, or None if the user aborted."""
    langs = available_languages()
    codes = [lang["code"] for lang in langs]
    suggested = current if current in codes else detect_system_language(available=codes)

    # The picker itself talks in the suggested language until a choice is made.
    previous = ctx.translator.language
    ctx.translator.language = suggested

    query = ""
    try:
        while True:
            shown = filter_languages(langs, query)
            ctx.print()
            ctx.print(ctx.t("picker.title"))
            if query:
                ctx.print(ctx.t("picker.filter", query=query))
            if not shown:
                ctx.print("  " + ctx.t("picker.no_match"))
            for i, lang in enumerate(shown, 1):
                marker = "*" if lang["code"] == suggested else " "
                extra = f" ({lang['english_name']})" if lang["english_name"] != lang["name"] else ""
                ctx.print(f" {marker}{i:>2}) {lang['name']}{extra} [{lang['code']}]")
            ctx.print(ctx.t("picker.hint"))

            answer = ctx.ask(ctx.t("picker.prompt") + " ")
            if answer is None:
                return None
            if answer == "":
                return shown[0]["code"] if query and len(shown) == 1 else suggested
            if answer.isdigit():
                n = int(answer)
                if 1 <= n <= len(shown):
                    return shown[n - 1]["code"]
                ctx.print(ctx.t("picker.invalid"))
                continue
            exact = _exact_match(langs, answer)
            if exact:
                return exact["code"]
            query = "" if answer in ("-", "*") else answer
    finally:
        ctx.translator.language = previous
