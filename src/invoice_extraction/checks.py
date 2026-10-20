"""Normalisation (to compare fairly) and plausibility checks (to decide what runs unattended)."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .schema import Invoice

AMOUNTS = ("net_total", "tax_total", "gross_total", "amount_due")


def amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    s = re.sub(r"[^\d,.\-]", "", str(value))
    if "," in s and "." in s:  # thousands separator: the last separator is the decimal one
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    for pattern, order in ((r"(\d{4})-(\d{2})-(\d{2})", "ymd"), (r"(\d{4})(\d{2})(\d{2})", "ymd"),
                           (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "dmy")):
        m = re.fullmatch(pattern, v)
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                return None
    return None


def text(value: str | None) -> str | None:
    return re.sub(r"[^0-9a-zäöüß]", "", value.casefold()) if value else None


def compact(value: str | None) -> str | None:
    return re.sub(r"\s", "", value).upper() if value else None


NORMALIZE = {
    "invoice_number": compact,
    "issue_date": iso_date,
    "seller_name": text,
    "seller_vat_id": compact,
    "buyer_name": text,
    "currency": compact,
    "iban": compact,
    **{f: amount for f in AMOUNTS},
}


CREDIT_NOTE = "381"
NAMES = ("seller_name", "buyer_name")
# Optional on an invoice: when the XML has no value we cannot tell whether the PDF shows one,
# so the field is not scored for that document.
OPTIONAL = ("seller_vat_id", "iban")

_LEGAL_FORM = re.compile(
    r"\s*,?\s*(gmbh\s*&\s*co\.?\s*kg|gmbh|ag|kg|ohg|e\.\s?k\.|ug|se|sarl|sas|sa|ltd\.?|inc\.?|llc)\.?$",
    re.IGNORECASE,
)


def _name_variants(value: str | None) -> set[str | None]:
    """XML name fields sometimes carry salutation or GLN lines ("Herrn\\nMax Mustermann");
    the last line is the name. Legal forms ("SARL", "GmbH") are ignored."""
    if not value:
        return {None}
    lines = [line for line in value.splitlines() if line.strip()]
    return {text(_LEGAL_FORM.sub("", v.strip())) for v in {value, lines[-1]}}


def field_matches(field: str, truth, pred, credit_note: bool = False) -> bool:
    if field in NAMES:
        return bool(_name_variants(truth) & _name_variants(pred))
    norm = NORMALIZE[field]
    if credit_note and field in AMOUNTS:
        # Credit notes: the XML states amounts as positive, the PDF often prints them negative.
        t, p = norm(truth), norm(pred)
        return t is not None and p is not None and abs(t) == abs(p)
    return norm(truth) == norm(pred)


def iban_valid(iban: str | None) -> bool:
    if not iban:
        return True  # no IBAN on the invoice is fine
    s = compact(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    digits = "".join(str(int(ch, 36)) for ch in s[4:] + s[:4])
    return int(digits) % 97 == 1


def plausibility(inv: Invoice) -> dict[str, bool]:
    """Checks that need no ground truth — they gate automatic processing."""
    net, tax, gross, due = (amount(getattr(inv, f)) for f in AMOUNTS)
    return {
        "betraege_lesbar": None not in (net, tax, gross, due),
        "netto_plus_steuer_gleich_brutto": None not in (net, tax, gross)
        and abs(net + tax - gross) <= Decimal("0.01"),
        "zahlbetrag_nicht_ueber_brutto": None not in (due, gross) and due <= gross,
        "datum_gueltig": iso_date(inv.issue_date) is not None,
        "iban_pruefziffer": iban_valid(inv.iban),
        "ustid_format": inv.seller_vat_id is None
        or re.fullmatch(r"[A-Z]{2}[0-9A-Z]{2,13}", compact(inv.seller_vat_id)) is not None,
    }
