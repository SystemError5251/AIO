# AIO-Website (GitHub Pages)

Statische Website mit Sprachwahl-Popup beim ersten Besuch und den Rechtstexten.
Keine Cookies, kein Tracking, keine externen Ressourcen.

## Veröffentlichen

Repository → **Settings → Pages** → Source „Deploy from a branch“, Branch `main`, Ordner `/docs`.
Die Seite erscheint danach unter `https://systemerror5251.github.io/AIO/`.

## Kontakt und Lizenz

Als Verantwortlicher steht der GitHub-Name `SystemError5251`, Kontakt läuft über GitHub Issues.
Es gibt bewusst keinen Klarnamen und keine Anschrift. Der Code steht unter MIT (`LICENSE`).

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

Ein Impressum ist bewusst nicht enthalten. Das ist für ein rein privates, unentgeltliches
Projekt ohne geschäftsmäßigen Charakter vertretbar (§ 5 DDG gilt für geschäftsmäßige, in der Regel
entgeltliche Dienste). Sobald das Projekt Einnahmen erzielt (Verkauf, Werbung, bezahlte Sponsorings)
oder gewerblich wird, muss ein Impressum mit ladungsfähiger Anschrift ergänzt werden.
