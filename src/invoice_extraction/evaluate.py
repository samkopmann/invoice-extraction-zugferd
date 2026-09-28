"""Compare predictions with the XML ground truth and simulate unattended processing."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .checks import field_matches, plausibility
from .schema import FIELDS, Invoice


def evaluate(truth: dict[str, Invoice], preds: dict[str, dict]) -> dict:
    """`preds[id]` = {"invoice": Invoice | None, "cost_usd", "seconds", ...}."""
    per_field = {f: [] for f in FIELDS}
    docs = []
    for doc_id, gt in truth.items():
        p = preds.get(doc_id)
        if p is None:
            continue
        inv = p["invoice"]
        correct = {f: inv is not None and field_matches(f, getattr(gt, f), getattr(inv, f))
                   for f in FIELDS}
        for f, ok in correct.items():
            per_field[f].append(ok)
        checks = plausibility(inv) if inv is not None else {"extrahiert": False}
        docs.append({
            "id": doc_id,
            "all_correct": all(correct.values()),
            "auto": all(checks.values()),
            "cost_usd": p.get("cost_usd", 0.0),
            "seconds": p.get("seconds", 0.0),
        })
    df = pd.DataFrame(docs)
    auto = df[df["auto"]] if len(df) else df
    return {
        "n": len(df),
        "field_accuracy": {f: float(np.mean(v)) for f, v in per_field.items() if v},
        "field_accuracy_mean": float(np.mean([np.mean(v) for v in per_field.values() if v])),
        "doc_all_correct": float(df["all_correct"].mean()) if len(df) else float("nan"),
        "auto_rate": float(df["auto"].mean()) if len(df) else float("nan"),
        "auto_precision": float(auto["all_correct"].mean()) if len(auto) else float("nan"),
        "cost_per_1000_usd": float(df["cost_usd"].mean() * 1000) if len(df) else float("nan"),
        "latency_p50_s": float(df["seconds"].median()) if len(df) else float("nan"),
        "latency_p95_s": float(df["seconds"].quantile(0.95)) if len(df) else float("nan"),
    }
