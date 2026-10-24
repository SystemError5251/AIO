"""Settings entry "Review translations": check machine-made and missing texts one by one."""

from __future__ import annotations

from typing import Any

from aio.core import review
from aio.core.context import AppContext
from aio.core.i18n import CORE_LOCALES_DIR, load_meta
from aio.tools.translate import DEFAULT_PLURAL_FORMS, PLURAL_FORMS, SOURCE_LANGS, placeholders


def _dirs(ctx: AppContext) -> list:
    return [CORE_LOCALES_DIR] + [p.locales_dir for p in ctx.plugins]


def open_count(ctx: AppContext) -> int | None:
    """Unchecked texts in the current language; None for the hand-written source languages."""
    lang = ctx.translator.language
    if lang in SOURCE_LANGS:
        return None
    return len(review.pending(_dirs(ctx), lang))


def _show(ctx: AppContext, key: str, value: Any) -> None:
    if isinstance(value, dict):
        ctx.print(ctx.t(key, text=""))
        for form, text in value.items():
            ctx.print(f"    {form}: {text}")
    else:
        ctx.print(ctx.t(key, text=value))


def _ask_value(ctx: AppContext, item: review.Item, lang: str) -> Any | None:
    """Ask for a new text (or every plural form). None = cancelled."""
    if not isinstance(item.source, dict):
        answer = ctx.ask(ctx.t("review.new_text") + " ")
        return answer or None
    value = {}
    for form in PLURAL_FORMS.get(lang, DEFAULT_PLURAL_FORMS):
        old = (item.current or {}).get(form) if isinstance(item.current, dict) else None
        answer = ctx.ask(ctx.t("review.new_form", form=form) + " ")
        if answer is None:
            return None
        if not answer:
            if not old:
                return None
            answer = old
        value[form] = answer
    return value


def _edit(ctx: AppContext, item: review.Item, lang: str) -> bool:
    while True:
        value = _ask_value(ctx, item, lang)
        if value is None:
            return False
        if review.check(item.source, value):
            review.correct(lang, item, value)
            ctx.print(ctx.t("review.saved"))
            return True
        names = ", ".join(sorted(placeholders(item.source))) or "–"
        ctx.print(ctx.t("review.invalid", placeholders=names))


def review_translations(ctx: AppContext) -> None:
    lang = ctx.translator.language
    name = load_meta().get(lang, {}).get("name", lang)
    ctx.print()
    ctx.print(f"== {ctx.t('review.title', language=name)} ==")
    if lang in SOURCE_LANGS:
        ctx.print(ctx.t("review.source_language", language=name))
        return
    items = review.pending(_dirs(ctx), lang)
    if not items:
        ctx.print(ctx.t("review.nothing", language=name))
        return
    ctx.print(ctx.t("review.intro", count=len(items)))
    done = 0
    for n, item in enumerate(items, 1):
        ctx.print()
        status = ctx.t(f"review.status_{item.status}")
        ctx.print(ctx.t("review.progress", n=n, total=len(items), id=item.key) + f" ({status})")
        _show(ctx, "review.source", item.source)
        if item.current is not None:
            _show(ctx, "review.current", item.current)
        actions = "review.actions" if item.status == "auto" else "review.actions_missing"
        answer = ctx.ask(ctx.t(actions) + " ")
        if answer is None or answer.lower() == "q":
            break
        answer = answer.lower()
        if answer == "" and item.status == "auto":
            review.accept(lang, item.key)
            done += 1
        elif answer == "e" and _edit(ctx, item, lang):
            done += 1
    ctx.translator.reload()
    ctx.print()
    if done:
        ctx.print(ctx.t("review.summary", count=done, path=str(review.overlay_path(lang))))
        ctx.print(ctx.t("review.share_hint"))
