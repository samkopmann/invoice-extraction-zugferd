"""LLM extraction with Claude: structured output validated against the `Invoice` schema.

Three input modes:
- `text`: the PDF's text layer (cheap, fails on scans)
- `pdf`:  the PDF itself as a document block (layout + images; attachments removed first)
- `scan`: every page rendered as a degraded grayscale image, like a scanned paper invoice
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass

import anthropic
import numpy as np
import pypdfium2 as pdfium
from PIL import Image

from .ground_truth import pdf_text, strip_attachments
from .schema import Invoice

DEFAULT_MODEL = "claude-opus-5-5"
MODES = ("text", "pdf", "scan")

# USD per million tokens (input, output) – see https://docs.claude.com/en/docs/about-claude/pricing
# Claude Haiku 5.5: rate for prompts up to 100K tokens (an invoice is far below that).
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Server-side fallback on a safety decline. Claude Haiku 5.5 has none: a fallback list
# returns a 400 there, so the parameter is only sent for these models.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

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


def scanned_pages(pdf: bytes, dpi: int = 150, seed: int = 0) -> list[bytes]:
    """Render each page like a mediocre office scan: grayscale, slightly rotated, a little
    noise, JPEG-compressed. Only pixels leave this function, so no text layer and no
    attachments (the answer key) can reach the model."""
    rng = np.random.default_rng(seed)
    pages = []
    doc = pdfium.PdfDocument(pdf)
    for page in doc:
        img = page.render(scale=dpi / 72, grayscale=True).to_pil().convert("L")
        img = img.rotate(float(rng.uniform(-1.2, 1.2)), expand=True, fillcolor=255,
                         resample=Image.BICUBIC)
        arr = np.asarray(img, dtype=np.float32) + rng.normal(0, 12, (img.height, img.width))
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55)
        pages.append(buf.getvalue())
    doc.close()
    return pages


class Extractor:
    def __init__(self, model: str = DEFAULT_MODEL, mode: str = "text", effort: str = "low",
                 client: anthropic.Anthropic | None = None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.model, self.mode, self.effort = model, mode, effort
        self.client = client or anthropic.Anthropic()

    def _content(self, pdf: bytes) -> list[dict]:
        if self.mode == "text":
            return [{"type": "text", "text": f"<rechnung>\n{pdf_text(pdf)}\n</rechnung>"}]
        if self.mode == "scan":
            images = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(jpg).decode()}}
                for jpg in scanned_pages(pdf)
            ]
            return [*images, {"type": "text", "text": "Extrahiere die Rechnungsdaten."}]
        data = base64.standard_b64encode(strip_attachments(pdf)).decode()
        return [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": "Extrahiere die Rechnungsdaten."},
        ]

    def __call__(self, pdf: bytes) -> Result:
        start = time.perf_counter()
        try:
            fallback = (
                {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                if self.model in FALLBACK_MODELS else {}
            )
            response = self.client.beta.messages.parse(
                model=self.model,
                # Thinking is always on for current models and counts toward max_tokens.
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": self._content(pdf)}],
                output_format=Invoice,
                output_config={"effort": self.effort},
                **fallback,
            )
        except anthropic.APIStatusError as exc:
            return Result(None, 0, 0, time.perf_counter() - start, 0.0, f"API {exc.status_code}")
        except anthropic.APIConnectionError:
            return Result(None, 0, 0, time.perf_counter() - start, 0.0, "API nicht erreichbar")
        seconds = time.perf_counter() - start
        usage = response.usage
        spent = cost(response.model, usage.input_tokens, usage.output_tokens)
        if response.stop_reason == "refusal":
            return Result(None, usage.input_tokens, usage.output_tokens, seconds, spent, "refusal")
        return Result(response.parsed_output, usage.input_tokens, usage.output_tokens, seconds,
                      spent, None if response.parsed_output else response.stop_reason)
