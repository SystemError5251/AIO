# Mitmachen

Zwei Wege: Übersetzungen verbessern oder ein eigenes Tool (Plugin) schreiben. Beides geht ohne Änderung am Kern.

## Übersetzungen

13 der 15 Sprachen sind maschinell übersetzt und als `"_auto"` markiert. Wer eine dieser Sprachen gut spricht, hilft am meisten so:

1. AIO auf die Sprache stellen und *Einstellungen → Übersetzungen prüfen* öffnen (oder `aio --review`).
2. Jeden Text mit Enter bestätigen oder mit `e` verbessern. Platzhalter wie `{count}` bleiben genau so stehen.
3. Die Datei `~/.aio/locales/<code>.json` in einem Issue mit der Vorlage „Übersetzung“ hochladen.

Maintainer übernehmen sie mit `python -m aio.tools.merge_review <datei>`. Geprüfte Texte verlieren dabei ihre `"_auto"`-Markierung, Texte mit falschen Platzhaltern werden übersprungen.

**Neue Sprache:** Eintrag in `aio/locales/_meta.json` (Name in eigener Schrift, `ltr` oder `rtl`), dann `python -m aio.tools.translate <code>` (braucht `ANTHROPIC_API_KEY`) oder die Dateien von Hand anlegen. `python -m aio.tools.check_locales` zeigt, was fehlt.

## Eigene Tools (Plugin-Schnittstelle)

```sh
python -m aio.tools.new_plugin mein_tool     # legt ~/.aio/plugins/mein_tool an
aio                                          # das Tool steht sofort in der Liste
```

Ein Plugin ist ein Ordner:

```
mein_tool/
  manifest.json   # id, version, api, name_key, desc_key, help_key, category, requires
  plugin.py       # def run(ctx): ...
  locales/de.json en.json   # Pflicht: mindestens Deutsch und Englisch
```

**manifest.json:** `id` (Kleinbuchstaben, Ziffern, `_`), `version`, `name_key`/`desc_key`/`help_key` (Textschlüssel für Name, Kurzbeschreibung in 1–2 Sätzen, ausführliche Hilfe). Optional: `api` (Version der Schnittstelle, aktuell `1`; ein Plugin mit höherer Zahl wird übersprungen, bis AIO aktualisiert ist), `category`, `requires` (Programme, z. B. `["ffmpeg"]`), `entry` (statt `plugin.py`).

**Was `run(ctx)` bekommt** (`aio/core/context.py`):

| Aufruf | Wirkung |
|---|---|
| `ctx.t(key, count=None, **werte)` | Text in der gewählten Sprache, mit Plural und Platzhaltern |
| `ctx.print(text)` | Ausgabe, bei Arabisch/Hebräisch rechtsbündig |
| `ctx.ask(prompt)` | Eine Eingabezeile; `None` bei Abbruch (Strg+D/Strg+C) |
| `ctx.ask_secret(prompt)` | Wie `ask`, aber ohne Anzeige der Eingabe (Passwörter) |
| `ctx.ask_file(prompt=None, allow_dir=False)` | Fragt nach einem vorhandenen Pfad; `None` = abgebrochen |
| `ctx.confirm(prompt)` | Ja/Nein in der Sprache des Nutzers |
| `ctx.translator.format_number(x)`, `format_date(d)` | Zahlen und Daten im Format der Sprache |
| `ctx.config` | Inhalt von `~/.aio/config.json` (nur lesen; schreiben mit `aio.core.config.set_value`) |

Für Medien gibt es `aio.core.media`: `probe(path)` (ffprobe), `ffmpeg(args)`, `require("ffmpeg")` (wirft `MissingTool`, AIO zeigt dann den passenden `pkg install`-Befehl), `output_path(src, suffix, ext)` (überschreibt nie etwas).

**Regeln:**
- Nichts überschreiben, Ergebnisse neben das Original legen.
- Alle Texte über `ctx.t()`, keine festen Strings. Schlüssel beginnen mit der Plugin-ID.
- Fehlende Programme mit `media.require()` prüfen statt abstürzen.

**Teilen:** Den Ordner als Git-Repository oder .zip veröffentlichen. Andere installieren es mit `aio --install-plugin <url-oder-pfad>` oder unter *Einstellungen → Plugins verwalten*. Ein Plugin ist Programmcode und läuft mit den Rechten des Nutzers. AIO warnt vor jeder Installation.

## Entwicklung

```sh
pip install -e ".[dev]" && pytest
python -m aio.tools.check_locales
```

Jeder neue Text braucht Deutsch und Englisch. Die übrigen Sprachen füllt `translate.py` (oder Claude im Projekt) nach und markiert sie als `"_auto"`.
