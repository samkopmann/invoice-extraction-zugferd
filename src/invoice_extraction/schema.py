"""The fields extracted from each invoice — identical for ground truth and LLM output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Invoice(BaseModel):
    invoice_number: str = Field(description="Rechnungsnummer, exakt wie gedruckt")
    issue_date: str = Field(description="Rechnungsdatum im Format YYYY-MM-DD")
    seller_name: str = Field(description="Name des Rechnungsstellers (Firma)")
    seller_vat_id: str | None = Field(description="USt-IdNr. des Verkäufers, z. B. DE123456789")
    buyer_name: str = Field(description="Name des Rechnungsempfängers (Firma)")
    currency: str = Field(description="ISO-4217-Währungscode, z. B. EUR")
    net_total: str = Field(description="Summe netto (Steuerbasis), Dezimalpunkt, z. B. 1234.50")
    tax_total: str = Field(description="Summe Umsatzsteuer, Dezimalpunkt")
    gross_total: str = Field(description="Gesamtbetrag brutto, Dezimalpunkt")
    amount_due: str = Field(description="Zahlbetrag (fällig), Dezimalpunkt")
    iban: str | None = Field(description="IBAN für die Zahlung, ohne Leerzeichen")


FIELDS = list(Invoice.model_fields)
