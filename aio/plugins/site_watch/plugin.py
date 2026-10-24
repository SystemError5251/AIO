"""Website-Wächter: check whether websites are up and whether their content changed.

For each saved URL: HTTP status, response time, and a fingerprint of the
visible text (scripts, styles and tags removed, whitespace collapsed), so
changing ads or tokens in the HTML do not count as a change. Optionally a
text that must appear on the page (e.g. "In stock"). Stored in config.json.
"""

from __future__ import annotations

import hashlib
import html
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from aio import __version__
from aio.core import config

CONFIG_KEY = "site_watch"
TIMEOUT = 15
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = f"AIO-site-watch/{__version__} (+https://github.com/SystemError5251/AIO)"


@dataclass
class Result:
    url: str
    status: int | None          # None = not reachable
    seconds: float
    fingerprint: str | None
    error: str = ""
    found: bool | None = None   # expected text present? None = no text set


def visible_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", body)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if re.match(r"^https?://", url, re.I) else "https://" + url


def fetch(url: str, expect: str = "", opener=None) -> Result:
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    start = time.monotonic()
    try:
        with opener(request, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES)
            status = resp.status
            charset = resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        return Result(url, exc.code, time.monotonic() - start, None, error=str(exc.reason))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return Result(url, None, time.monotonic() - start, None, error=str(reason))
    text = visible_text(raw.decode(charset, errors="replace"))
    found = (expect.casefold() in text.casefold()) if expect else None
    return Result(url, status, time.monotonic() - start, fingerprint(text), found=found)


def sites() -> list[dict]:
    return [s for s in config.load().get(CONFIG_KEY, []) if isinstance(s, dict) and s.get("url")]


def save_sites(items: list[dict]) -> None:
    config.set_value(CONFIG_KEY, items)


def check_all(items: list[dict], fetcher=fetch) -> list[tuple[dict, Result, list[str]]]:
    """Fetch every site; returns (site, result, notes) and updates the stored fingerprints."""
    out = []
    for site in items:
        result = fetcher(site["url"], site.get("expect", ""))
        notes = []
        if result.status is None:
            notes.append("site_watch.down")
        elif result.status >= 400:
            notes.append("site_watch.http_error")
        else:
            old = site.get("fingerprint")
            if old and result.fingerprint != old:
                notes.append("site_watch.changed")
            elif old:
                notes.append("site_watch.unchanged")
            else:
                notes.append("site_watch.first_check")
            site["fingerprint"] = result.fingerprint
            if result.found is True:
                notes.append("site_watch.text_found")
            elif result.found is False:
                notes.append("site_watch.text_missing")
        site["checked"] = int(time.time())
        out.append((site, result, notes))
    return out


def _report(ctx, rows) -> None:
    for site, result, notes in rows:
        ctx.print()
        ctx.print(site["url"])
        if result.status is not None:
            ctx.print("  " + ctx.t("site_watch.status", status=result.status,
                                   ms=int(result.seconds * 1000)))
        for key in notes:
            mark = "✓" if key in ("site_watch.unchanged", "site_watch.first_check",
                                  "site_watch.text_found") else "!"
            ctx.print(f"  {mark} " + ctx.t(key, error=result.error, text=site.get("expect", "")))


def run(ctx):
    while True:
        items = sites()
        ctx.print()
        if items:
            ctx.print(ctx.t("site_watch.list_title"))
            for i, site in enumerate(items, 1):
                extra = f"  [{site['expect']}]" if site.get("expect") else ""
                ctx.print(f"   {i}) {site['url']}{extra}")
            ctx.print("   c) " + ctx.t("site_watch.check"))
        else:
            ctx.print(ctx.t("site_watch.none_yet"))
        ctx.print("   n) " + ctx.t("site_watch.add"))
        if items:
            ctx.print("   r) " + ctx.t("site_watch.remove"))
        ctx.print("   b) " + ctx.t("menu.back"))
        answer = (ctx.ask(ctx.t("menu.prompt") + " ") or "b").lower()
        if answer in ("b", "q"):
            return
        if answer == "n":
            url = ctx.ask(ctx.t("site_watch.ask_url") + " ")
            if not url:
                continue
            expect = ctx.ask(ctx.t("site_watch.ask_text") + " ") or ""
            items.append({"url": normalize_url(url), "expect": expect})
            ctx.print(ctx.t("site_watch.checking"))
            _report(ctx, check_all(items[-1:]))
            save_sites(items)
        elif answer == "c" and items:
            ctx.print(ctx.t("site_watch.checking"))
            _report(ctx, check_all(items))
            save_sites(items)
        elif answer == "r" and items:
            pick = ctx.ask(ctx.t("site_watch.remove_prompt") + " ")
            if pick and pick.isdigit() and 1 <= int(pick) <= len(items):
                removed = items.pop(int(pick) - 1)
                save_sites(items)
                ctx.print(ctx.t("site_watch.removed", url=removed["url"]))
        else:
            ctx.print(ctx.t("menu.invalid"))
