"""Avaliacao dos agentes contra o GROUND TRUTH injetado pelo gerador (eixo 4).

Mede, de forma reprodutivel:
  - deteccao: precisao e recall (o sentinela pegou as anomalias certas?)
  - RCA: acuracia do no suspeito vs causa raiz real.

`--check` faz o processo falhar (exit 1) se cair abaixo do limite -> vira gate de
regressao no CI a cada mudanca de prompt/modelo/baseline.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.common.llm import LLMClient              # noqa: E402
from agents.common.settings import settings          # noqa: E402
from agents.detectors import statistical             # noqa: E402
from agents.tools import metrics as metrics_tool     # noqa: E402
from agents.tools.dbt_lineage import Lineage         # noqa: E402
from agents import rca                               # noqa: E402

RECALL_MIN = 0.99
RCA_MIN = 0.66
FALLBACK_EDGES = {
    "mart_metrics": ["int_transactions_enriched", "stg_marketing"],
    "int_transactions_enriched": ["stg_transactions"],
    "stg_transactions": ["raw_transactions"],
    "stg_marketing": ["raw_marketing_spend"],
    "stg_users": ["raw_users"],
}


def _load_truth() -> list[dict]:
    return json.loads(settings.manifest_path.read_text())


def _in_window(d: date, window: list[str]) -> bool:
    lo, hi = date.fromisoformat(window[0]), date.fromisoformat(window[1])
    return lo <= d <= hi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="falha se abaixo do limite")
    args = ap.parse_args()

    truth = _load_truth()
    llm = LLMClient()
    try:
        lineage = Lineage.from_manifest()
    except FileNotFoundError:
        lineage = Lineage.from_edges(FALLBACK_EDGES)

    # roda o detector em cada metrica vigiada
    detected = []
    for metric in metrics_tool.list_metrics():
        detected.extend(statistical.detect(metrics_tool.get_series(metric)))

    # ---- deteccao: TP/FP/FN ----
    tp_signals = sum(
        1 for s in detected
        if any(a["metric"] == s.metric_name and _in_window(s.metric_date, a["window"])
               for a in truth)
    )
    fp_signals = len(detected) - tp_signals
    matched = sum(
        1 for a in truth
        if any(s.metric_name == a["metric"] and _in_window(s.metric_date, a["window"])
               for s in detected)
    )
    recall = matched / len(truth) if truth else 0.0
    precision = tp_signals / (tp_signals + fp_signals) if detected else 0.0

    # ---- RCA: no suspeito vs causa raiz ----
    rca_total = rca_ok = 0
    for a in truth:
        sig = next((s for s in detected
                    if s.metric_name == a["metric"] and _in_window(s.metric_date, a["window"])),
                   None)
        if sig is None:
            continue
        rca_total += 1
        h = rca.diagnose(sig, lineage, llm)
        rca_ok += int(h.suspected_node == a["root_cause_node"])
    rca_acc = rca_ok / rca_total if rca_total else 0.0

    print("=== Evals · Sentinela de Dados (Mar) ===")
    print(f"anomalias (ground truth): {len(truth)} | sinais detectados: {len(detected)}")
    print(f"deteccao  -> recall={recall:.0%}  precisao={precision:.0%}")
    print(f"RCA       -> acuracia do no suspeito={rca_acc:.0%} ({rca_ok}/{rca_total})")

    if args.check:
        ok = recall >= RECALL_MIN and rca_acc >= RCA_MIN
        print("RESULTADO:", "PASSOU" if ok else "FALHOU")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
