"""LLM extraction with Claude: structured output validated against the `Invoice` schema.

Two input modes:
- `text`: the PDF's text layer (cheap, fails on scans)
- `pdf`:  the PDF itself as a document block (layout + images; attachments removed first)
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass

import anthropic

from .ground_truth import pdf_text, strip_attachments
from .schema import Invoice

DEFAULT_MODEL = "claude-opus-5"

# USD per million tokens (input, output) – see https://docs.claude.com/en/docs/about-claude/pricing
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

SYSTEM = (
    "Du extrahierst Rechnungsdaten aus deutschen und europäischen Rechnungen für die "
    "automatische Buchung. Übernimm Werte exakt so, wie sie auf der Rechnung stehen – "
    "rechne nichts aus und ergänze nichts. Beträge mit Dezimalpunkt ohne Tausendertrennzeichen "
    "(z. B. 1234.50), Datum als YYYY-MM-DD. Felder, die auf der Rechnung nicht vorkommen, "
    "sind null."
)


@dataclass
class Result:
    invoice: Invoice | None
    input_tokens: int
    output_tokens: int
    seconds: float
    cost_usd: float
    error: str | None = None


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, (float("nan"), float("nan")))
    return (input_tokens * p_in + output_tokens * p_out) / 1e6


class Extractor:
    def __init__(self, model: str = DEFAULT_MODEL, mode: str = "text", effort: str = "low",
                 client: anthropic.Anthropic | None = None):
        if mode not in ("text", "pdf"):
            raise ValueError("mode must be 'text' or 'pdf'")
        self.model, self.mode, self.effort = model, mode, effort
        self.client = client or anthropic.Anthropic()

    def _content(self, pdf: bytes) -> list[dict]:
        if self.mode == "text":
            return [{"type": "text", "text": f"<rechnung>\n{pdf_text(pdf)}\n</rechnung>"}]
        data = base64.standard_b64encode(strip_attachments(pdf)).decode()
        return [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": "Extrahiere die Rechnungsdaten."},
        ]

    def __call__(self, pdf: bytes) -> Result:
        start = time.perf_counter()
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM,
                messages=[{"role": "user", "content": self._content(pdf)}],
                output_format=Invoice,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            return Result(None, 0, 0, time.perf_counter() - start, 0.0, f"API {exc.status_code}")
        seconds = time.perf_counter() - start
        usage = response.usage
        spent = cost(response.model, usage.input_tokens, usage.output_tokens)
        if response.stop_reason == "refusal":
            return Result(None, usage.input_tokens, usage.output_tokens, seconds, spent, "refusal")
        return Result(response.parsed_output, usage.input_tokens, usage.output_tokens, seconds,
                      spent, None if response.parsed_output else response.stop_reason)
