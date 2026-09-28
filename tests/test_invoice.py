import base64
import io
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter

from invoice_extraction import checks
from invoice_extraction.evaluate import evaluate
from invoice_extraction.extract import Extractor
from invoice_extraction.ground_truth import (
    UnsupportedInvoice,
    embedded_xml,
    parse_cii,
    strip_attachments,
)
from invoice_extraction.schema import Invoice

CII = b"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
  xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocument>
    <ram:ID>RE-2024-0815</ram:ID>
    <ram:IssueDateTime><udt:DateTimeString format="102">20240315</udt:DateTimeString></ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>Lieferant GmbH</ram:Name>
        <ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">201/113/40209</ram:ID></ram:SpecifiedTaxRegistration>
        <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">DE123456789</ram:ID></ram:SpecifiedTaxRegistration>
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty><ram:Name>Kunde AG</ram:Name></ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
      <ram:SpecifiedTradeSettlementPaymentMeans>
        <ram:PayeePartyCreditorFinancialAccount><ram:IBANID>DE89370400440532013000</ram:IBANID></ram:PayeePartyCreditorFinancialAccount>
      </ram:SpecifiedTradeSettlementPaymentMeans>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:TaxBasisTotalAmount>1000.00</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">190.00</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>1190.00</ram:GrandTotalAmount>
        <ram:DuePayableAmount>1190.00</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


def _pdf_with_attachment(xml: bytes) -> bytes:
    w = PdfWriter()
    w.add_blank_page(595, 842)
    w.add_attachment("factur-x.xml", xml)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_parse_cii():
    inv = parse_cii(CII)
    assert inv.invoice_number == "RE-2024-0815"
    assert inv.issue_date == "2024-03-15"
    assert inv.seller_vat_id == "DE123456789"  # VA, not the tax number (FC)
    assert inv.gross_total == "1190.00"
    assert inv.iban == "DE89370400440532013000"


def test_rejects_non_cii():
    with pytest.raises(UnsupportedInvoice):
        parse_cii(b"<Invoice xmlns='urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'/>")


def test_attachment_roundtrip_and_strip():
    pdf = _pdf_with_attachment(CII)
    assert embedded_xml(pdf) == CII
    assert b"/EmbeddedFile" in pdf
    stripped = strip_attachments(pdf)
    assert PdfReader(io.BytesIO(stripped)).attachments == {}
    assert b"/EmbeddedFile" not in stripped  # orphaned file stream removed too
    with pytest.raises(UnsupportedInvoice):
        embedded_xml(stripped)


@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("1234,5", "1234.50"),
    ("EUR 99.90", "99.90"), ("-10,00", "-10.00"),
])
def test_amount_normalisation(raw, expected):
    assert checks.amount(raw) == Decimal(expected)


def test_dates_and_text():
    assert checks.iso_date("15.03.2024") == "2024-03-15"
    assert checks.iso_date("20240315") == "2024-03-15"
    assert checks.iso_date("31.02.2024") is None
    assert checks.field_matches("seller_name", "Lieferant GmbH", "LIEFERANT GMBH.")


def test_iban_and_plausibility():
    assert checks.iban_valid("DE89 3704 0044 0532 0130 00")
    assert not checks.iban_valid("DE89370400440532013001")
    good = parse_cii(CII)
    assert all(checks.plausibility(good).values())
    bad = good.model_copy(update={"tax_total": "19.00"})
    assert not checks.plausibility(bad)["netto_plus_steuer_gleich_brutto"]


def test_evaluate_gate():
    gt = parse_cii(CII)
    wrong_but_plausible = gt.model_copy(update={"buyer_name": "Andere AG"})
    implausible = gt.model_copy(update={"iban": "DE00370400440532013000"})
    r = evaluate(
        {"a": gt, "b": gt, "c": gt},
        {"a": {"invoice": gt, "cost_usd": 0.01, "seconds": 1.0},
         "b": {"invoice": wrong_but_plausible, "cost_usd": 0.01, "seconds": 2.0},
         "c": {"invoice": implausible, "cost_usd": 0.01, "seconds": 3.0}},
    )
    assert r["doc_all_correct"] == pytest.approx(1 / 3)
    assert r["auto_rate"] == pytest.approx(2 / 3)
    assert r["auto_precision"] == pytest.approx(1 / 2)
    assert r["cost_per_1000_usd"] == pytest.approx(10.0)


class _FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed, self.stop_reason, self.kwargs = parsed, stop_reason, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            model=kwargs["model"], stop_reason=self.stop_reason, parsed_output=self.parsed,
            usage=SimpleNamespace(input_tokens=2000, output_tokens=200),
        )


def test_extractor_request_and_cost():
    fake = _FakeMessages(parse_cii(CII))
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    pdf = _pdf_with_attachment(CII)
    r = Extractor(model="claude-opus-5", mode="pdf", client=client)(pdf)
    assert isinstance(r.invoice, Invoice)
    assert r.cost_usd == pytest.approx((2000 * 5 + 200 * 25) / 1e6)
    assert fake.kwargs["output_format"] is Invoice
    assert fake.kwargs["fallbacks"] == "default"
    doc = fake.kwargs["messages"][0]["content"][0]
    assert doc["type"] == "document"  # attachment stripped before upload
    assert b"/EmbeddedFile" not in base64.b64decode(doc["source"]["data"])


def test_extractor_refusal():
    fake = _FakeMessages(None, stop_reason="refusal")
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    r = Extractor(client=client)(_pdf_with_attachment(CII))
    assert r.invoice is None and r.error == "refusal"
