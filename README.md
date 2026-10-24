# AIO

Modulares All-in-One-Toolkit für Termux und Python. Mehrere Einzeltools (Video, Upload, Datenschutz und mehr) unter einer Oberfläche. Vor dem Start wählst du deine Sprache, und jedes Tool erklärt sich in dieser Sprache. Läuft offline, ohne Konto und ohne Tracking.

*Modular all-in-one toolkit for Termux & Python. Pick your language before the UI starts; every tool explains itself in that language. Works offline, no account, no tracking. Install with the two commands below.*

🌐 Website: <https://systemerror5251.github.io/AIO/>

## Installation (Termux)

Termux aus [F-Droid](https://f-droid.org/packages/com.termux/) installieren, dann:

```sh
pkg install -y curl
curl -fsSL https://raw.githubusercontent.com/SystemError5251/AIO/main/aio-installer.sh | bash
```

Das Skript installiert Python, git, ffmpeg und termux-api, lädt AIO nach `~/.aio/src` und richtet den Befehl `aio` ein. **Update:** in AIO unter Einstellungen → „Jetzt nach Updates suchen“ oder mit `aio --update`. Unter „Automatische Updates“ stellst du ein, ob AIO beim Start prüft (aus, nur Bescheid geben oder automatisch installieren) und wie oft (jeder Start, täglich, wöchentlich). Ohne Internet startet AIO ganz normal. Alternativ denselben Installationsbefehl erneut ausführen. Funktioniert genauso unter Linux (dort Python 3.11+, git und ffmpeg vorher selbst installieren).

Einmalig empfohlen:

```sh
termux-setup-storage   # Zugriff auf Fotos/Videos (~/storage/dcim/Camera)
```

Für das Teilen-Menü zusätzlich die App **Termux:API** aus F-Droid installieren.

<details>
<summary>Manuell installieren</summary>

```sh
pkg install python python-pip git ffmpeg termux-api
git clone https://github.com/SystemError5251/AIO.git && pip install ./AIO
```
</details>

## Benutzung

| Befehl | Wirkung |
|---|---|
| `aio` | Beim ersten Start Sprachwahl, danach Hauptmenü |
| `aio --lang` | Sprachwahl erneut anzeigen (auch: `--choose-language`) |
| `aio --lang de` | Sprache direkt setzen |
| `aio --list` | Tools auflisten |
| `aio --review` | Übersetzungen der eingestellten Sprache prüfen |

Die Sprache lässt sich auch unter *Einstellungen → Sprache ändern* wechseln. Vorgeschlagen wird die Systemsprache. Einstellungen liegen in `~/.aio/config.json`.

## Enthaltene Tools

| Tool | Was es macht | Braucht |
|---|---|---|
| Privacy-Stripper | Entfernt GPS-, Geräte- und Zeitdaten aus Fotos (verlustfrei) und Videos (ohne Neukodierung), einzeln oder ganze Ordner | ffmpeg (für Videos) |
| Musik-Check | Misst Lautheit (LUFS) gegen die −14 LUFS der Plattformen, speichert auf Wunsch eine korrigierte Kopie; optional Songerkennung | ffmpeg; optional `pkg install chromaprint` + AcoustID-Schlüssel |
| Upload (Reels/Shorts/TikTok) | Prüft Format, Länge und Codecs, wandelt bei Bedarf in 1080×1920 um und öffnet das Android-Teilen-Menü | ffmpeg, termux-api + App Termux:API |
| Untertitel | Prüft eine .srt/.vtt/.ass-Datei und brennt sie ein oder fügt sie als abschaltbare Spur hinzu | ffmpeg |
| Lautheit angleichen | Bringt ganze Ordner auf −14, −16 oder −23 LUFS (zwei Durchgänge, Bild unverändert) | ffmpeg |
| Zuschneiden | Schneidet auf 9:16, 1:1, 4:5 oder 16:9 zu (Mitte, links/oben, rechts/unten) und kürzt Anfang/Ende | ffmpeg |

Ergebnisse landen neben dem Original (`clip.clean.mp4`, `clip.loudnorm.mp4`, `clip.tiktok.mp4`, `clip.crop.mp4` …). Es wird nie etwas überschrieben.

## Sprachen

15 Sprachen sind enthalten: Deutsch und Englisch von Hand, dazu Arabisch, Chinesisch, Französisch, Hebräisch, Hindi, Italienisch, Japanisch, Polnisch, Portugiesisch, Russisch, Spanisch, Türkisch und Ukrainisch als maschinelle Übersetzung. Maschinell übersetzte Texte stehen in jeder Datei unter `"_auto"`. `python -m aio.tools.check_locales` zählt, wie viele noch offen sind.

**Übersetzungen prüfen:** Unter *Einstellungen → Übersetzungen prüfen* (oder `aio --review`) zeigt AIO jeden ungeprüften Text der eingestellten Sprache neben dem Englischen. Enter bestätigt, `e` ändert, `s` überspringt. Auch fehlende Texte lassen sich so übersetzen. Platzhalter wie `{count}` müssen erhalten bleiben. Korrekturen landen in `~/.aio/locales/<code>.json`, gelten sofort und überstehen Updates. Wer die Datei teilt (z. B. in einem Issue), hilft allen: `python -m aio.tools.merge_review fr.json` übernimmt sie ins Repository und nimmt die geprüften Texte aus `"_auto"`.

Arabisch und Hebräisch werden rechtsbündig ausgegeben (Flag `dir` in `_meta.json`).

## Erweitern

**Neue Sprache:** Eintrag in `aio/locales/_meta.json` (Name in eigener Schrift, `ltr`/`rtl`), dann die Texte erzeugen lassen oder `aio/locales/<code>.json` von Hand anlegen:

```sh
pip install -e ".[translate]"
export ANTHROPIC_API_KEY=...
python -m aio.tools.translate nl          # nur fehlende Texte, mit Cache
python -m aio.tools.translate --dry-run   # zeigt nur, was fehlt
```

`translate.py` schickt nur fehlende Schlüssel an die Claude-API, merkt sich Ergebnisse in `~/.aio/translate_cache.json` und markiert alles Neue als `"_auto"`. Fehlende Texte fallen zur Laufzeit auf Englisch und danach auf den Schlüsselnamen zurück.

**Neues Tool:** Ordner in `aio/plugins/` oder `~/.aio/plugins/` mit `manifest.json`, `plugin.py` (Funktion `run(ctx)`) und `locales/de.json` + `en.json`. Vorlage: `aio/plugins/demo_hello`.

**Entwicklung:**

```sh
pip install -e ".[dev]" && pytest
python -m aio.tools.check_locales   # fehlende Übersetzungen melden
```

## Rechtliches

[Rechtliche Hinweise](https://systemerror5251.github.io/AIO/rechtliche-hinweise.html) · [Datenschutz](https://systemerror5251.github.io/AIO/datenschutz.html) · [Nutzungsbedingungen](https://systemerror5251.github.io/AIO/nutzungsbedingungen.html)

Lizenz: [MIT](LICENSE). Fragen und Fehler bitte über [GitHub Issues](https://github.com/SystemError5251/AIO/issues).
