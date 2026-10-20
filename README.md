# Rechnungsextraktion mit LLMs – gemessen statt geschätzt

Ein LLM liest Rechnungs-PDFs und liefert strukturierte Daten für die Buchung. Die Frage,
die in fast jedem Projekt offen bleibt: **Wie gut ist das wirklich – Feld für Feld?**

Dieses Projekt nutzt einen Trick des deutschen Marktes: **ZUGFeRD-/Factur-X-Rechnungen**
enthalten dieselben Daten zweimal – als lesbares PDF und als eingebettetes XML nach
EN 16931 (UN/CEFACT CII). Das Modell sieht nur das PDF, das XML dient als Lösungsschlüssel.
So entsteht eine Genauigkeitsmessung ohne manuelles Labeln.

> Daten: [ZUGFeRD-Korpus](https://github.com/ZUGFeRD/corpus) (Apache 2.0), darin die
> offiziellen Musterrechnungen des FeRD (frei nutzbar nach FeRD-Lizenz). `make data` klont ihn in dem Stand,
> mit dem die Ergebnisse entstanden sind (Commit `82e886f`, 13.10.2026). Die PDFs liegen nicht in diesem Repository.

## Ergebnis

**25 Musterrechnungen**, je drei Eingabevarianten, zwei Modelle (Oktober 2026):

| Modell | Eingabe | Feldgenauigkeit | Beleg komplett richtig | Fehler bei Dunkelverarbeitung | Kosten pro 1.000 Belege | Latenz (Median) |
|---|---|---|---|---|---|---|
| Claude Haiku 5.5 | Textebene | 100,0 % | 25 / 25 | 0 | $ 0,35 | 1,7 s |
| Claude Haiku 5.5 | PDF | 100,0 % | 25 / 25 | 0 | $ 0,75 | 1,9 s |
| Claude Haiku 5.5 | **Scan** | 99,6 % | 24 / 25 | 0 | $ 0,95 | 2,3 s |
| Claude Opus 5.5 | Textebene | 98,9 % | 24 / 25 | 0 | $ 13,03 | 2,7 s |
| Claude Opus 5.5 | PDF | 98,9 % | 24 / 25 | 0 | $ 29,36 | 3,5 s |
| Claude Opus 5.5 | **Scan** | 98,9 % | 24 / 25 | 0 | $ 37,13 | 4,1 s |

Vollständige Tabellen inkl. Genauigkeit je Feld: [`results/evaluation.md`](results/evaluation.md).

Einordnung:

- **Das kleine Modell reicht.** Auf diesen Rechnungen ist Haiku 5.5 mindestens so genau wie
  Opus 5.5 – bei rund 1/40 der Kosten. Genau diese Frage beantwortet ein Testset: Welches Modell
  ist für *diese* Aufgabe gut genug?
- **Gescannte Rechnungen funktionieren.** Ohne Textebene, leicht schief und verrauscht, sinkt
  die Genauigkeit kaum. Der einzige Scan-Fehler: ein fehlendes Minuszeichen bei der Steuer einer
  Rechnungskorrektur.
- **Die Prüfregeln halten.** Kein Beleg, der alle Plausibilitätsprüfungen bestand, war falsch.
  68 % der Belege wären vollautomatisch durchgelaufen, der Rest ging zur Prüfung – fast
  ausschließlich, weil die Musterrechnungen erfundene IBANs mit ungültiger Prüfziffer enthalten.
  Die IBAN-Prüfung hat also genau das getan, wofür sie da ist.
- **Ein echtes Risiko, das die Zahlen nicht zeigen:** Bei vier Versicherungsrechnungen mit
  Lastschrift lesen beide Modelle die IBAN *des Kunden* als Zahlungs-IBAN. Hier fing die
  Prüfziffer das ab (Muster-IBAN), mit einer echten Kunden-IBAN wäre es durchgerutscht. Im
  Projekt heißt das: Lastschrift erkennen oder die IBAN gegen den Lieferantenstamm prüfen.

**Grenzen:** 25 Rechnungen sind eine kleine Stichprobe, und Musterrechnungen sind aufgeräumter
als der typische Posteingang (handschriftliche Notizen, Mehrseiter mit Anlagen, schlechte
Fotos). Das Ergebnis zeigt, dass der Ansatz trägt und wie man ihn misst – nicht, wie gut er auf
Ihren Belegen ist. Das klärt ein Testset aus Ihren eigenen Rechnungen.

### Wie die Grundwahrheit bereinigt wurde

Aus 151 PDFs im Korpus bleiben 25 eindeutige Rechnungen. Ausgeschlossen werden Testdateien für
Validatoren (Ordner `fail/`), ZUGFeRD 1.0, die Profile MINIMUM und BASIC WL (deren XML enthält
absichtlich nur wenige Felder), Duplikate (dieselbe Musterrechnung liegt in mehreren Ordnern)
und zwei Dateien, deren PDF eine andere Rechnung zeigt als das angehängte XML.

Beim Vergleich gelten feste Regeln für alle Modelle gleich. Sie wurden **nach** Durchsicht der
Abweichungen im ersten Lauf festgelegt, weil der Lösungsschlüssel dort selbst ungenau war:

| Regel | Grund |
|---|---|
| Mehrzeilige Namen im XML: letzte Zeile zählt, Rechtsform wird ignoriert | XML enthält z. B. „Herrn\nMax Mustermann“ oder GLN-Zeilen vor dem Firmennamen |
| Gutschriften (Typ 381): Beträge ohne Vorzeichen | Im XML positiv, auf dem PDF oft negativ gedruckt |
| USt-IdNr. und IBAN nur bewerten, wenn das XML sie enthält | Fehlt der Wert im XML, ist unklar, ob er auf der Rechnung steht |

## Was gemessen wird

| Kennzahl | Bedeutung |
|---|---|
| Feldgenauigkeit | Anteil korrekt extrahierter Felder (nach fairer Normalisierung: Datumsformat, Dezimaltrennzeichen, Groß-/Kleinschreibung) |
| Beleg komplett richtig | alle 11 Felder korrekt |
| Automatisch verarbeitbar | Anteil der Belege, die **alle Plausibilitätsprüfungen** bestehen – ohne Grundwahrheit, wie im Echtbetrieb |
| Fehlerquote automatisch | Anteil fehlerhafter Belege *unter* den automatisch verarbeiteten – das eigentliche Risiko |
| Kosten und Latenz | aus den Token-Angaben der API |

**Plausibilitätsprüfungen** (entscheiden über Dunkelverarbeitung vs. Prüfliste):
Netto + Steuer = Brutto, Zahlbetrag ≤ Brutto, gültiges Datum, IBAN-Prüfziffer (Modulo 97),
Format der USt-IdNr.

Extrahierte Felder: Rechnungsnummer, -datum, Verkäufer, USt-IdNr., Käufer, Währung,
Netto, Steuer, Brutto, Zahlbetrag, IBAN.

## Varianten

- `--mode text`: Textebene des PDFs → günstig, scheitert an Scans
- `--mode pdf`: das PDF selbst (Layout und Bild) → robuster, teurer. Eingebettete
  Dateien werden **vor** dem Upload entfernt, damit das Modell den Lösungsschlüssel nicht sieht.
- `--mode scan`: jede Seite als Graustufenbild, leicht gedreht, verrauscht, JPEG-komprimiert –
  wie ein mittelmäßiger Büroscan. Das Modell sieht nur Pixel.
- `--model`: jedes Claude-Modell, z. B. `claude-opus-5-5`, `claude-sonnet-5-5`,
  `claude-haiku-5-5` – so wird der Preis-Leistungs-Vergleich direkt messbar.

Technik: Claude mit Structured Outputs (`messages.parse` gegen ein Pydantic-Schema) –
die Antwort ist garantiert schema-konform, es gibt kein fehleranfälliges JSON-Parsen.

## Reproduzieren

```bash
uv sync --extra dev
echo 'ANTHROPIC_API_KEY=...' > .env  # oder export / `ant auth login`
make data                           # Korpus klonen + Grundwahrheit aus XML erzeugen
uv run invoice-extraction extract --limit 10              # erst Kosten prüfen
uv run invoice-extraction extract                         # alle Belege, Textmodus
uv run invoice-extraction extract --mode pdf              # PDF-Modus
uv run invoice-extraction extract --mode scan             # Scan-Variante
uv run invoice-extraction extract --model claude-haiku-5-5
make evaluate
make test                                                 # ohne API-Zugang lauffähig
```

Läufe sind fortsetzbar – bereits verarbeitete Belege werden übersprungen.

## Code

```
src/invoice_extraction/
  schema.py        Zielschema (Pydantic)
  ground_truth.py  XML-Anhang lesen, CII parsen, Anhänge entfernen
  extract.py       Claude-Extraktion (Text, PDF oder Scan), Kosten, Latenz
  checks.py        Normalisierung und Plausibilitätsprüfungen
  evaluate.py      Feldgenauigkeit, Automatisierungsquote, Fehlerquote
```

## Übertragbarkeit

Eingangsrechnungen, Lieferscheine, Auftragsbestätigungen: Das Muster – Schema,
Plausibilitätsprüfung, Schwelle für Dunkelverarbeitung, Messung gegen Grundwahrheit –
ist dasselbe. Seit 2025 müssen Unternehmen in Deutschland E-Rechnungen empfangen können;
für alle anderen Belege bleibt die Extraktion aus PDFs.

---
Dr. Samuel Kopmann · [softwareandmore.de/ai-integration](https://softwareandmore.de/ai-integration)

© 2026 Dr. Samuel Kopmann. Alle Rechte vorbehalten. Der Code ist zum Ansehen und Nachrechnen der
Ergebnisse veröffentlicht; für eine Nutzung in eigenen Projekten sprechen Sie mich gern an.
