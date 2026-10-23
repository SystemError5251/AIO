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
  core/       main.py, config.py, i18n.py, registry.py, context.py, ui/
  locales/    de.json, en.json, _meta.json (Name in eigener Schrift, ltr/rtl)
  plugins/    demo_hello/, demo_sysinfo/  (Vorlagen für echte Tools)
  tools/      check_locales.py
tests/
```

### Neue Sprache hinzufügen

1. Eintrag in `aio/locales/_meta.json` (falls noch nicht vorhanden)
2. `aio/locales/<code>.json` anlegen – fertig, kein Code nötig.

Fehlende Texte fallen auf Englisch und danach auf den Schlüsselnamen zurück.

### Neues Tool (Plugin)

Ein Ordner in `aio/plugins/` oder `~/.aio/plugins/` mit:

- `manifest.json` – `id`, `version`, `name_key`, `desc_key`, `help_key` (optional `category`, `requires`, `entry`)
- `plugin.py` – Funktion `run(ctx)`; `ctx.t()`, `ctx.print()`, `ctx.ask()` stehen bereit
- `locales/de.json`, `locales/en.json` – Pflicht, bevor ein Tool in `main` kommt

`demo_hello` ist die Vorlage.

## Entwicklung

```sh
pip install -e ".[dev]"
pytest
python -m aio.tools.check_locales   # meldet fehlende Schlüssel je Sprache
```
