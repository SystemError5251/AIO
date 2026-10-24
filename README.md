# AIO

Modulares All-in-One-Toolkit für Termux und Python: Video-Pipeline, Upload, Backups, Tracker und mehr unter einer Oberfläche. Vor dem Start der UI wählst du deine Sprache, und jedes Tool bringt eine Kurzerklärung in dieser Sprache mit. Plugin-basiert und leicht erweiterbar.

*Modular all-in-one toolkit for Termux & Python. Pick your language before the UI starts; every tool ships with short explanations in many languages.*

## Installation (Termux)

```sh
pkg install python git
git clone https://github.com/SystemError5251/AIO.git
cd AIO
pip install -e .            # ohne Zusatzpakete lauffähig
pip install -e ".[locale]"  # optional: babel für Plural- und Datumsformate
```

## Tools

| Tool | Was es macht | Braucht |
|---|---|---|
| Privacy-Stripper | Entfernt GPS-, Geräte- und Zeitdaten aus Fotos (JPEG/PNG, verlustfrei) und Videos (ohne Neukodierung). Einzelne Datei oder ganzer Ordner. | ffmpeg (für Videos) |
| Musik-Check | Misst Lautheit (LUFS) und Spitzenpegel gegen die -14 LUFS der Plattformen, speichert auf Wunsch eine korrigierte Kopie. Optional Songerkennung über AcoustID. | ffmpeg; optional chromaprint + AcoustID-Schlüssel |
| Upload (Reels/Shorts/TikTok) | Prüft Format, Länge, Codecs und Bildrate, wandelt bei Bedarf in 1080x1920 um und öffnet das Android-Teilen-Menü. | ffmpeg; zum Teilen termux-api + App Termux:API |

```sh
pkg install ffmpeg            # für alle Video-Tools
pkg install termux-api        # Teilen-Menü (plus App „Termux:API“ aus F-Droid)
pkg install chromaprint       # optional: Songerkennung
termux-setup-storage          # Zugriff auf ~/storage/dcim/Camera usw.
```

Ergebnisse landen immer neben dem Original (`clip.clean.mp4`, `clip.loudnorm.mp4`, `clip.tiktok.mp4`); nichts wird überschrieben. Die Grenzen der Plattformen stehen in `aio/plugins/video_upload/platforms.json` und lassen sich ohne Code anpassen.

## Benutzung

| Befehl | Wirkung |
|---|---|
| `aio` | Beim ersten Start Sprachwahl, danach Hauptmenü |
| `aio --lang` / `aio --choose-language` | Sprachwahl erneut anzeigen |
| `aio --lang de` | Sprache direkt setzen |
| `aio --list` | Tools auflisten und beenden |

Im Sprachwahl-Bildschirm: Zahl = wählen, Text = suchen (z. B. `deu`, `german`, `de`), Enter = markierte Sprache übernehmen. Vorgeschlagen wird die Systemsprache aus `LC_ALL`/`LC_MESSAGES`/`LANG`. Die Wahl landet in `~/.aio/config.json` und lässt sich auch unter *Einstellungen → Sprache ändern* ändern.

## Aufbau

```
aio/
  core/       main.py, config.py, i18n.py, registry.py, context.py, media.py, ui/
  locales/    de.json, en.json, _meta.json (Name in eigener Schrift, ltr/rtl)
  plugins/    privacy_strip/, music_check/, video_upload/, demo_hello/ (Vorlage), demo_sysinfo/
  tools/      check_locales.py, translate.py
tests/
```

### Sprachen

15 Sprachen sind enthalten: Deutsch und Englisch von Hand, dazu Arabisch, Chinesisch, Französisch, Hebräisch, Hindi, Italienisch, Japanisch, Polnisch, Portugiesisch, Russisch, Spanisch, Türkisch und Ukrainisch als maschinelle Übersetzung. Maschinell übersetzte Texte stehen in jeder Datei unter `"_auto"`. Wer einen Text geprüft hat, nimmt ihn dort heraus. `python -m aio.tools.check_locales` zählt, wie viele noch offen sind.

Arabisch und Hebräisch werden rechtsbündig ausgegeben (Flag `dir` in `_meta.json`).

### Neue Sprache hinzufügen

1. Eintrag in `aio/locales/_meta.json` (Name in eigener Schrift, `ltr`/`rtl`)
2. Texte erzeugen lassen – oder `aio/locales/<code>.json` von Hand anlegen:

```sh
pip install -e ".[translate]"
export ANTHROPIC_API_KEY=...
python -m aio.tools.translate nl          # nur fehlende Texte, mit Cache
python -m aio.tools.translate --dry-run   # zeigt nur, was fehlt
```

`translate.py` schickt nur fehlende Schlüssel an die Claude-API, merkt sich Ergebnisse in `~/.aio/translate_cache.json` und markiert alles Neue als `"_auto"`. Fehlende Texte fallen zur Laufzeit auf Englisch und danach auf den Schlüsselnamen zurück.

### Neues Tool (Plugin)

Ein Ordner in `aio/plugins/` oder `~/.aio/plugins/` mit:

- `manifest.json` – `id`, `version`, `name_key`, `desc_key`, `help_key` (optional `category`, `requires`, `entry`)
- `plugin.py` – Funktion `run(ctx)`; `ctx.t()`, `ctx.print()`, `ctx.ask()`, `ctx.ask_file()`, `ctx.confirm()` stehen bereit, für Videos `aio.core.media`
- `locales/de.json`, `locales/en.json` – Pflicht, bevor ein Tool in `main` kommt

`demo_hello` ist die Vorlage.

## Entwicklung

```sh
pip install -e ".[dev]"
pytest
python -m aio.tools.check_locales   # meldet fehlende Schlüssel je Sprache
```
