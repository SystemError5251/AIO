"""Settings entry "System check" and `aio --doctor`."""

from __future__ import annotations

from aio.core import config, doctor
from aio.core.context import AppContext


def _tool_names(ctx: AppContext, ids: list[str]) -> str:
    names = {p.id: ctx.t(p.name_key) for p in ctx.plugins}
    return ", ".join(names[i] for i in ids if i in names) or "AIO"


def report(ctx: AppContext) -> list[doctor.Check]:
    checks = doctor.run_checks(ctx.config)
    ctx.print()
    ctx.print(f"== {ctx.t('doctor.title')} ==")
    for check in checks:
        mark = "✓" if check.ok else ("○" if check.optional else "✗")
        ctx.print(f" {mark} {check.name}  ({_tool_names(ctx, check.tools)})")
        if not check.ok:
            ctx.print("     " + ctx.t(check.hint, **check.values))
    missing = [c for c in checks if not c.ok and not c.optional]
    ctx.print()
    if missing:
        ctx.print(ctx.t("doctor.summary", count=len(missing)))
    else:
        ctx.print(ctx.t("doctor.all_ok"))
    return checks


def set_acoustid_key(ctx: AppContext) -> None:
    key = ctx.ask(ctx.t("doctor.ask_acoustid") + " ")
    if not key:
        return
    ctx.print(ctx.t("doctor.testing_key"))
    result = doctor.verify_acoustid_key(key)
    if result is False:
        ctx.print(ctx.t("doctor.key_rejected"))
        return
    ctx.config = config.set_value("acoustid_key", key)
    ctx.print(ctx.t("doctor.key_saved" if result else "doctor.key_saved_untested"))


def system_check(ctx: AppContext) -> list[doctor.Check]:
    checks = report(ctx)
    acoustid = next(c for c in checks if c.name == "acoustid")
    if not acoustid.ok:
        set_acoustid_key(ctx)
    return checks
