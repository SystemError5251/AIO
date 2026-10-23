"""Dummy plugin: prints basic facts about the device."""

import os
import platform
import shutil


def run(ctx):
    home = os.path.expanduser("~")
    free_gb = shutil.disk_usage(home).free / 1024**3
    ctx.print(ctx.t("demo_sysinfo.python", version=platform.python_version()))
    ctx.print(ctx.t("demo_sysinfo.system", system=f"{platform.system()} {platform.machine()}"))
    ctx.print(ctx.t("demo_sysinfo.termux", value=ctx.t(
        "demo_sysinfo.yes" if "com.termux" in os.environ.get("PREFIX", "") else "demo_sysinfo.no")))
    ctx.print(ctx.t("demo_sysinfo.disk", free=ctx.translator.format_number(round(free_gb, 1))))
