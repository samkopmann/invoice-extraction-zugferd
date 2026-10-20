# Ergebnis Rechnungsextraktion

Grundwahrheit: 25 ZUGFeRD-/Factur-X-Rechnungen mit eingebettetem CII-XML.

| Lauf | n | Ø Feldgenauigkeit | Beleg komplett richtig | Automatisch verarbeitbar | Fehlerquote automatisch | $ / 1.000 Belege | Latenz p50 |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5_pdf | 25 | 100.0% | 100.0% | 68.0% | 0.0% | 0.75 | 1.9 s |
| claude-haiku-5-5_scan | 25 | 99.6% | 96.0% | 64.0% | 0.0% | 0.95 | 2.3 s |
| claude-haiku-5-5_text | 25 | 100.0% | 100.0% | 68.0% | 0.0% | 0.35 | 1.7 s |
| claude-opus-5-5_pdf | 25 | 98.9% | 96.0% | 68.0% | 0.0% | 29.36 | 3.5 s |
| claude-opus-5-5_scan | 25 | 98.9% | 96.0% | 68.0% | 0.0% | 37.13 | 4.1 s |
| claude-opus-5-5_text | 25 | 98.9% | 96.0% | 68.0% | 0.0% | 13.03 | 2.7 s |

## Genauigkeit je Feld

| Lauf | invoice_number | issue_date | seller_name | seller_vat_id | buyer_name | currency | net_total | tax_total | gross_total | amount_due | iban |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5_pdf | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| claude-haiku-5-5_scan | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 96.0% | 100.0% | 100.0% | 100.0% |
| claude-haiku-5-5_text | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| claude-opus-5-5_pdf | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 87.5% |
| claude-opus-5-5_scan | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 87.5% |
| claude-opus-5-5_text | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 87.5% |
