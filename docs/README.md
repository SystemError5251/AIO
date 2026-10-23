# AIO-Website (GitHub Pages)

Statische Website mit Sprachwahl-Popup beim ersten Besuch und den Rechtstexten.
Keine Cookies, kein Tracking, keine externen Ressourcen.

## Veröffentlichen

Repository → **Settings → Pages** → Source „Deploy from a branch“, Branch `main`, Ordner `/docs`.
Die Seite erscheint danach unter `https://systemerror5251.github.io/AIO/`.

## Vor dem Veröffentlichen ausfüllen

Alle gelb markierten Platzhalter `[...]` ersetzen:

- [ ] Name und ladungsfähige Anschrift (kein Postfach) in `impressum.html`, `datenschutz.html`, `nutzungsbedingungen.html`
- [ ] E-Mail-Adresse und einen zweiten schnellen Kontaktweg (z. B. Telefon)
- [ ] Zuständige Landesdatenschutzbehörde in `datenschutz.html`
- [ ] Lizenz (und eine passende `LICENSE`-Datei im Repo-Root anlegen)
- [ ] „Stand“-Datum in Datenschutz und Nutzungsbedingungen

Suchen: `grep -n 'class="ph"' docs/*.html`

## Sprachen

Die Sprachwahl wird nur im `localStorage` des Browsers gespeichert (`aio-lang`).
Neue Sprache: Eintrag in `LANGS` in `assets/lang.js` und in jeder Seite einen Block
`<section data-l="xx">` ergänzen. Fehlt ein Block, wird Englisch, dann Deutsch angezeigt.
Rechtlich verbindlich ist die deutsche Fassung.

## Hinweis

Die Texte sind sorgfältig erstellte **Vorlagen und keine Rechtsberatung**. Sie passen für ein
kostenloses Open-Source-Projekt ohne Tracking. Wenn du Geld verlangst (Verkauf, Abos, Spenden mit
Gegenleistung), Werbung oder Analyse-Tools einbaust, ein Kontaktformular oder Newsletter anbietest,
brauchst du zusätzliche Texte (z. B. Widerrufsbelehrung, Einwilligungsbanner). Lass die Texte im
Zweifel von einer Anwältin, einem Anwalt oder einem Generator-Dienst prüfen.
