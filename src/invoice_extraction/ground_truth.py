"""Ground truth from the XML embedded in ZUGFeRD 2.x / Factur-X / XRechnung-CII PDFs.

A hybrid e-invoice carries the same data twice: as a human-readable PDF and as a
machine-readable UN/CEFACT Cross Industry Invoice (CII) XML attachment. The LLM only sees
the PDF; the XML is the answer key.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject

from .schema import Invoice

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
_TX = "rsm:SupplyChainTradeTransaction/"
_AGR = _TX + "ram:ApplicableHeaderTradeAgreement/"
_SET = _TX + "ram:ApplicableHeaderTradeSettlement/"
_SUM = _SET + "ram:SpecifiedTradeSettlementHeaderMonetarySummation/"


class UnsupportedInvoice(ValueError):
    pass


def embedded_xml(pdf: bytes) -> bytes:
    """The CII XML attachment of a hybrid invoice PDF."""
    reader = PdfReader(io.BytesIO(pdf))
    for name, contents in reader.attachments.items():
        for content in contents:
            if name.lower().endswith(".xml") and b"CrossIndustry" in content[:4000]:
                return content
    raise UnsupportedInvoice("keine CII-XML-Anlage gefunden")


def strip_attachments(pdf: bytes) -> bytes:
    """Rebuild the PDF from its pages only — no embedded files, so the answer key is gone.

    Document-level attachments live in the catalog, which is not copied. Page-level
    associated files and file-attachment annotations are removed explicitly.
    """
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        if "/AF" in page:
            del page["/AF"]
        if "/Annots" in page:
            kept = [a for a in page["/Annots"] if a.get_object().get("/Subtype") != "/FileAttachment"]
            page[NameObject("/Annots")] = ArrayObject(kept)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _text(root: ET.Element, path: str) -> str | None:
    el = root.find(path, NS)
    return el.text.strip() if el is not None and el.text else None


def parse_cii(xml: bytes) -> Invoice:
    root = ET.fromstring(xml)
    if root.tag != f"{{{NS['rsm']}}}CrossIndustryInvoice":
        raise UnsupportedInvoice(f"kein CII 100 (ZUGFeRD 2.x): {root.tag}")
    currency = _text(root, _SET + "ram:InvoiceCurrencyCode") or "EUR"
    # TaxTotalAmount may appear twice (invoice and accounting currency) – take the invoice one.
    tax = None
    for el in root.findall(_SUM + "ram:TaxTotalAmount", NS):
        if tax is None or el.get("currencyID") == currency:
            tax = el.text.strip()
    date_raw = _text(root, "rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString") or ""
    required = {
        "invoice_number": _text(root, "rsm:ExchangedDocument/ram:ID"),
        "seller_name": _text(root, _AGR + "ram:SellerTradeParty/ram:Name"),
        "buyer_name": _text(root, _AGR + "ram:BuyerTradeParty/ram:Name"),
        "gross_total": _text(root, _SUM + "ram:GrandTotalAmount"),
    }
    if not all(required.values()) or len(date_raw) != 8:
        raise UnsupportedInvoice("Pflichtfelder fehlen im XML")
    return Invoice(
        **required,
        issue_date=f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}",
        seller_vat_id=_text(
            root, _AGR + "ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"
        ),
        currency=currency,
        net_total=_text(root, _SUM + "ram:TaxBasisTotalAmount") or "0",
        tax_total=tax or "0",
        amount_due=_text(root, _SUM + "ram:DuePayableAmount") or required["gross_total"],
        iban=_text(
            root,
            _SET + "ram:SpecifiedTradeSettlementPaymentMeans/"
            "ram:PayeePartyCreditorFinancialAccount/ram:IBANID",
        ),
    )


def pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
