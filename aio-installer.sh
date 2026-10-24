#!/usr/bin/env bash
# AIO installieren oder aktualisieren (Termux und Linux).
#   curl -fsSL https://raw.githubusercontent.com/SystemError5251/AIO/main/aio-installer.sh | bash
# Erneut ausführen = Update. Zielordner per AIO_SRC änderbar (Standard: ~/.aio/src).
set -euo pipefail

REPO="${AIO_REPO:-https://github.com/SystemError5251/AIO.git}"
BRANCH="${AIO_BRANCH:-main}"
SRC="${AIO_SRC:-$HOME/.aio/src}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

if [ -n "${TERMUX_VERSION:-}" ] || command -v termux-info >/dev/null 2>&1; then
    say "Termux erkannt: installiere python, git, ffmpeg, termux-api"
    pkg install -y python python-pip git ffmpeg termux-api python-cryptography
else
    for cmd in python3 git; do
        command -v "$cmd" >/dev/null 2>&1 || { echo "Fehlt: $cmd – bitte zuerst installieren." >&2; exit 1; }
    done
    command -v ffmpeg >/dev/null 2>&1 || echo "Hinweis: ffmpeg fehlt, die Video-Tools brauchen es."
fi

PY="$(command -v python3 || command -v python)"
"$PY" -m pip --version >/dev/null 2>&1 || "$PY" -m ensurepip --upgrade

if [ -d "$SRC/.git" ]; then
    say "Aktualisiere $SRC"
    git -C "$SRC" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC" reset --hard "origin/$BRANCH"
else
    say "Lade AIO nach $SRC"
    mkdir -p "$(dirname "$SRC")"
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$SRC"
fi

say "Installiere den Befehl aio"
if [ -n "${TERMUX_VERSION:-}" ] || command -v termux-info >/dev/null 2>&1; then
    "$PY" -m pip install --upgrade "$SRC"
else
    "$PY" -m pip install --user --upgrade "$SRC" \
        || "$PY" -m pip install --user --break-system-packages --upgrade "$SRC"
fi

say "Fertig. Starten mit:  aio"
command -v aio >/dev/null 2>&1 || echo "Falls 'aio' nicht gefunden wird: ~/.local/bin zum PATH hinzufügen oder 'python3 -m aio' nutzen."
