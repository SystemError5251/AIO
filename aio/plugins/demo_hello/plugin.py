"""Dummy plugin: template for real tools. Shows texts, plurals and formats."""


def run(ctx):
    name = ctx.ask(ctx.t("demo_hello.ask_name") + " ") or ctx.t("demo_hello.stranger")
    ctx.print(ctx.t("demo_hello.greeting", name=name))
    ctx.print(ctx.t("demo_hello.today", date=ctx.translator.format_date()))
    for n in (1, 3):
        ctx.print(ctx.t("demo_hello.files", count=n))
