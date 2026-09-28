# Rechnungsextraktion mit LLMs – gemessen statt geschätzt

Ein LLM liest Rechnungs-PDFs und liefert strukturierte Daten für die Buchung. Die Frage,
die in fast jedem Projekt offen bleibt: **Wie gut ist das wirklich – Feld für Feld?**

Dieses Projekt nutzt einen Trick des deutschen Marktes: **ZUGFeRD-/Factur-X-Rechnungen**
enthalten dieselben Daten zweimal – als lesbares PDF und als eingebettetes XML nach
EN 16931 (UN/CEFACT CII). Das Modell sieht nur das PDF, das XML dient als Lösungsschlüssel.
So entsteht eine Genauigkeitsmessung ohne manuelles Labeln.

> Daten: öffentliche Beispiel- und Praxisrechnungen aus dem
> [ZUGFeRD-Korpus](https://github.com/ZUGFeRD/corpus). `make data` klont ihn.

## Ergebnis

<!-- Wird von `make evaluate` in results/evaluation.md erzeugt – Tabelle hier einfügen. -->
_Noch nicht ausgeführt – siehe [Reproduzieren](#reproduzieren)._

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
- `--model`: jedes Claude-Modell, z. B. `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5`
  – so wird der Preis-Leistungs-Vergleich direkt messbar.

Technik: Claude mit Structured Outputs (`messages.parse` gegen ein Pydantic-Schema) –
die Antwort ist garantiert schema-konform, es gibt kein fehleranfälliges JSON-Parsen.

## Reproduzieren

```bash
uv sync --extra dev
export ANTHROPIC_API_KEY=...        # oder `ant auth login`
make data                           # Korpus klonen + Grundwahrheit aus XML erzeugen
uv run invoice-extraction extract --limit 10              # erst Kosten prüfen
uv run invoice-extraction extract                         # alle Belege, Textmodus
uv run invoice-extraction extract --mode pdf              # PDF-Modus
uv run invoice-extraction extract --model claude-haiku-4-5
make evaluate
make test                                                 # ohne API-Zugang lauffähig
```

Läufe sind fortsetzbar – bereits verarbeitete Belege werden übersprungen.

## Code

```
src/invoice_extraction/
  schema.py        Zielschema (Pydantic)
  ground_truth.py  XML-Anhang lesen, CII parsen, Anhänge entfernen
  extract.py       Claude-Extraktion (Text oder PDF), Kosten, Latenz
  checks.py        Normalisierung und Plausibilitätsprüfungen
  evaluate.py      Feldgenauigkeit, Automatisierungsquote, Fehlerquote
```

## Übertragbarkeit

Eingangsrechnungen, Lieferscheine, Auftragsbestätigungen: Das Muster – Schema,
Plausibilitätsprüfung, Schwelle für Dunkelverarbeitung, Messung gegen Grundwahrheit –
ist dasselbe. Seit 2025 müssen Unternehmen in Deutschland E-Rechnungen empfangen können;
für alle anderen Belege bleibt die Extraktion aus PDFs.

---
Samuel Kopmann · [softwareandmore.de/ai-integration](https://softwareandmore.de/ai-integration)
