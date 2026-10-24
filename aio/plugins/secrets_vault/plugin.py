"""Secrets-Tresor: keep API keys, passwords and tokens encrypted on the phone.

The vault is one file, ~/.aio/vault.json. Its content is encrypted with
AES-256-GCM; the key comes from the master password via scrypt (n=2^15, r=8),
so guessing passwords is slow. Without the password the file is useless, and
any change to it is detected. Needs the `cryptography` package
(Termux: pkg install python-cryptography). The master password cannot be
recovered: forget it and the secrets are gone.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from aio.core import config, media

VERSION = 1
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
MIN_PASSWORD = 8
TRIES = 3


class WrongPassword(Exception):
    pass


def vault_path() -> Path:
    return config.aio_home() / "vault.json"


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return None
    return AESGCM


def available() -> bool:
    return _aesgcm() is not None


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _key(password: str, salt: bytes, params: dict[str, int]) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params["n"], r=params["r"],
                          p=params["p"], maxmem=128 * 1024 * 1024, dklen=32)


def encrypt(entries: dict[str, str], password: str) -> dict[str, Any]:
    salt, nonce = os.urandom(16), os.urandom(12)
    header = {"v": VERSION, "kdf": "scrypt", **SCRYPT, "salt": _b64(salt)}
    aad = json.dumps(header, sort_keys=True).encode()
    data = _aesgcm()(_key(password, salt, SCRYPT)).encrypt(
        nonce, json.dumps(entries, ensure_ascii=False).encode("utf-8"), aad)
    return {**header, "nonce": _b64(nonce), "data": _b64(data)}


def decrypt(blob: dict[str, Any], password: str) -> dict[str, str]:
    from cryptography.exceptions import InvalidTag
    header = {k: blob[k] for k in ("v", "kdf", "n", "r", "p", "salt")}
    aad = json.dumps(header, sort_keys=True).encode()
    key = _key(password, base64.b64decode(blob["salt"]), blob)
    try:
        plain = _aesgcm()(key).decrypt(base64.b64decode(blob["nonce"]),
                                       base64.b64decode(blob["data"]), aad)
    except InvalidTag as exc:
        raise WrongPassword from exc
    return json.loads(plain.decode("utf-8"))


def load(password: str) -> dict[str, str]:
    return decrypt(json.loads(vault_path().read_text("utf-8")), password)


def save(entries: dict[str, str], password: str) -> None:
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(encrypt(entries, password), fh)
    os.replace(tmp, path)


def copy_to_clipboard(value: str) -> bool:
    if not media.has("termux-clipboard-set"):
        return False
    return subprocess.run(["termux-clipboard-set"], input=value, text=True,
                          check=False).returncode == 0


def _new_password(ctx) -> str | None:
    while True:
        first = ctx.ask_secret(ctx.t("secrets_vault.new_password", min=MIN_PASSWORD) + " ")
        if not first:
            return None
        if len(first) < MIN_PASSWORD:
            ctx.print(ctx.t("secrets_vault.too_short", min=MIN_PASSWORD))
            continue
        if ctx.ask_secret(ctx.t("secrets_vault.repeat_password") + " ") == first:
            return first
        ctx.print(ctx.t("secrets_vault.mismatch"))


def _unlock(ctx) -> tuple[str, dict[str, str]] | None:
    if not vault_path().exists():
        ctx.print(ctx.t("secrets_vault.create_intro"))
        password = _new_password(ctx)
        if password is None:
            return None
        save({}, password)
        ctx.print(ctx.t("secrets_vault.created", path=str(vault_path())))
        return password, {}
    for _ in range(TRIES):
        password = ctx.ask_secret(ctx.t("secrets_vault.ask_password") + " ")
        if not password:
            return None
        try:
            return password, load(password)
        except WrongPassword:
            ctx.print(ctx.t("secrets_vault.wrong_password"))
    return None


def _pick(ctx, names: list[str]) -> str | None:
    answer = ctx.ask(ctx.t("secrets_vault.which") + " ")
    if answer and answer.isdigit() and 1 <= int(answer) <= len(names):
        return names[int(answer) - 1]
    return None


def run(ctx):
    if not available():
        ctx.print(ctx.t("secrets_vault.need_crypto"))
        return
    unlocked = _unlock(ctx)
    if unlocked is None:
        return
    password, entries = unlocked
    while True:
        names = sorted(entries, key=str.casefold)
        ctx.print()
        ctx.print(ctx.t("secrets_vault.count", count=len(names)))
        for i, name in enumerate(names, 1):
            ctx.print(f"   {i}) {name}")
        ctx.print("   c) " + ctx.t("secrets_vault.copy"))
        ctx.print("   s) " + ctx.t("secrets_vault.show"))
        ctx.print("   n) " + ctx.t("secrets_vault.add"))
        ctx.print("   d) " + ctx.t("secrets_vault.delete"))
        ctx.print("   p) " + ctx.t("secrets_vault.change_password"))
        ctx.print("   b) " + ctx.t("secrets_vault.lock"))
        answer = (ctx.ask(ctx.t("menu.prompt") + " ") or "b").lower()
        if answer in ("b", "q"):
            ctx.print(ctx.t("secrets_vault.locked"))
            return
        if answer == "n":
            name = ctx.ask(ctx.t("secrets_vault.ask_name") + " ")
            if not name:
                continue
            if name in entries and not ctx.confirm(ctx.t("secrets_vault.overwrite", name=name)):
                continue
            value = ctx.ask_secret(ctx.t("secrets_vault.ask_value") + " ")
            if not value:
                continue
            entries[name] = value
            save(entries, password)
            ctx.print(ctx.t("secrets_vault.saved", name=name))
        elif answer in ("c", "s", "d") and names:
            name = _pick(ctx, names)
            if name is None:
                continue
            if answer == "c":
                done = copy_to_clipboard(entries[name])
                ctx.print(ctx.t("secrets_vault.copied" if done else "secrets_vault.no_clipboard"))
            elif answer == "s":
                ctx.print(f"   {name}: {entries[name]}")
            elif ctx.confirm(ctx.t("secrets_vault.confirm_delete", name=name)):
                del entries[name]
                save(entries, password)
                ctx.print(ctx.t("secrets_vault.deleted", name=name))
        elif answer == "p":
            new = _new_password(ctx)
            if new:
                password = new
                save(entries, password)
                ctx.print(ctx.t("secrets_vault.password_changed"))
        else:
            ctx.print(ctx.t("menu.invalid"))
