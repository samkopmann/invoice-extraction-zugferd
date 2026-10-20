"""Command line: `invoice-extraction corpus | groundtruth | extract | evaluate`."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from .checks import CREDIT_NOTE, compact
from .evaluate import evaluate
from .extract import DEFAULT_MODEL, MODES, Extractor, Result
from .ground_truth import (
    INCOMPLETE_PROFILES,
    UnsupportedInvoice,
    embedded_xml,
    parse_cii,
    pdf_text,
    profile,
    type_code,
)
from .schema import FIELDS, Invoice

DATA = Path("data")
CORPUS = DATA / "corpus"
GT = DATA / "groundtruth.jsonl"
RESULTS = Path("results")
CORPUS_REPO = "https://github.com/ZUGFeRD/corpus.git"
# Pinned so the 25 invoices and the published results stay reproducible as the corpus grows.
CORPUS_COMMIT = "82e886fb21369e3e83c1e97170a4ff406deceee7"


def _doc_id(path: Path) -> str:
    return hashlib.sha1(str(path.relative_to(CORPUS)).encode()).hexdigest()[:12]


def cmd_corpus(_args) -> None:
    if not CORPUS.exists():
        subprocess.run(["git", "clone", "--no-checkout", CORPUS_REPO, str(CORPUS)], check=True)
    git = ["git", "-C", str(CORPUS)]
    subprocess.run([*git, "fetch", "--quiet", "origin", CORPUS_COMMIT], check=True)
    subprocess.run([*git, "checkout", "--quiet", "--detach", CORPUS_COMMIT], check=True)


def cmd_groundtruth(_args) -> None:
    stats, seen = Counter(), set()
    with GT.open("w", encoding="utf-8") as out:
        for path in sorted(CORPUS.rglob("*.pdf")):
            if "fail" in path.relative_to(CORPUS).parts:
                stats["ausgeschlossen: Testdatei für Validatoren (fail/)"] += 1
                continue
            pdf = path.read_bytes()
            try:
                xml = embedded_xml(pdf)
                inv = parse_cii(xml)
            except UnsupportedInvoice as exc:
                stats[str(exc).split(":")[0]] += 1
                continue
            except Exception:  # noqa: BLE001 – broken PDFs exist in the corpus
                stats["PDF nicht lesbar"] += 1
                continue
            if (prof := profile(xml)) in INCOMPLETE_PROFILES:
                stats[f"ausgeschlossen: Profil {prof} (XML unvollständig)"] += 1
                continue
            # Answer-key consistency: a few corpus files carry the XML of a different invoice
            # than the one printed on the PDF.
            if compact(inv.invoice_number) not in compact(pdf_text(pdf)):
                stats["ausgeschlossen: PDF zeigt andere Rechnung als das XML"] += 1
                continue
            # The same sample invoice appears in several folders of the corpus.
            key = (inv.invoice_number, inv.seller_name, inv.gross_total)
            if key in seen:
                stats["ausgeschlossen: Duplikat"] += 1
                continue
            seen.add(key)
            has_text = len(pdf_text(pdf).strip()) > 50
            stats["ok" if has_text else "ok (ohne Textebene)"] += 1
            out.write(json.dumps({"id": _doc_id(path), "path": str(path), "has_text": has_text,
                                  "profile": prof, "type_code": type_code(xml),
                                  "truth": inv.model_dump()},
                                 ensure_ascii=False) + "\n")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"→ {GT}")


def _load_truth() -> list[dict]:
    return [json.loads(line) for line in GT.open(encoding="utf-8")]


def _pred_path(model: str, mode: str) -> Path:
    return RESULTS / f"predictions_{model}_{mode}.jsonl"


def cmd_extract(args) -> None:
    RESULTS.mkdir(exist_ok=True)
    out_path = _pred_path(args.model, args.mode)
    done = {json.loads(line)["id"] for line in out_path.open()} if out_path.exists() else set()
    docs = [d for d in _load_truth() if (d["has_text"] or args.mode != "text") and d["id"] not in done]
    docs = docs[: args.limit] if args.limit else docs
    extractor = Extractor(model=args.model, mode=args.mode, effort=args.effort)
    with out_path.open("a", encoding="utf-8") as out:
        for i, d in enumerate(docs, 1):
            try:
                r = extractor(Path(d["path"]).read_bytes())
            except Exception as exc:  # noqa: BLE001 – one unreadable document must not stop the run
                r = Result(None, 0, 0, 0.0, 0.0, f"{type(exc).__name__}: {exc}"[:200])
            out.write(json.dumps({
                "id": d["id"],
                "invoice": r.invoice.model_dump() if r.invoice else None,
                "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                "seconds": r.seconds, "cost_usd": r.cost_usd, "error": r.error,
            }, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i}/{len(docs)}] {Path(d['path']).name}: {'ok' if r.invoice else r.error}")


def cmd_evaluate(_args) -> None:
    docs = _load_truth()
    truth = {d["id"]: Invoice(**d["truth"]) for d in docs}
    credit_notes = {d["id"] for d in docs if d.get("type_code") == CREDIT_NOTE}
    lines = [
        "# Ergebnis Rechnungsextraktion\n",
        f"Grundwahrheit: {len(truth)} ZUGFeRD-/Factur-X-Rechnungen mit eingebettetem CII-XML.\n",
        ("| Lauf | n | Ø Feldgenauigkeit | Beleg komplett richtig | Automatisch verarbeitbar "
         "| Fehlerquote automatisch | $ / 1.000 Belege | Latenz p50 |"),
        "|---|---|---|---|---|---|---|---|",
    ]
    field_rows = []
    for path in sorted(RESULTS.glob("predictions_*.jsonl")):
        preds = {}
        for line in path.open(encoding="utf-8"):
            p = json.loads(line)
            p["invoice"] = Invoice(**p["invoice"]) if p["invoice"] else None
            preds[p["id"]] = p
        run = path.stem.removeprefix("predictions_")
        r = evaluate(truth, preds, credit_notes)
        lines.append(
            f"| {run} | {r['n']} | {r['field_accuracy_mean']:.1%} | {r['doc_all_correct']:.1%} "
            f"| {r['auto_rate']:.1%} | {1 - r['auto_precision']:.1%} "
            f"| {r['cost_per_1000_usd']:.2f} | {r['latency_p50_s']:.1f} s |"
        )
        field_rows.append(f"| {run} | " + " | ".join(
            f"{r['field_accuracy'].get(f, float('nan')):.1%}" for f in FIELDS) + " |")
    lines += ["", "## Genauigkeit je Feld", "", "| Lauf | " + " | ".join(FIELDS) + " |",
              "|---|" + "---|" * len(FIELDS), *field_rows, ""]
    (RESULTS / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def _load_dotenv(path: Path = Path(".env")) -> None:
    """KEY=value lines from .env into the environment; existing variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> None:
    _load_dotenv()
    p = argparse.ArgumentParser(prog="invoice-extraction")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("corpus", help="ZUGFeRD-Korpus klonen").set_defaults(func=cmd_corpus)
    sub.add_parser("groundtruth", help="XML aus PDFs lesen").set_defaults(func=cmd_groundtruth)
    e = sub.add_parser("extract", help="LLM-Extraktion (kostet API-Guthaben)")
    e.add_argument("--model", default=DEFAULT_MODEL)
    e.add_argument("--mode", choices=MODES, default="text")
    e.add_argument("--effort", choices=["low", "medium", "high"], default="low")
    e.add_argument("--limit", type=int, help="nur N Belege (Kosten testen)")
    e.set_defaults(func=cmd_extract)
    sub.add_parser("evaluate").set_defaults(func=cmd_evaluate)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
