"""Entrypoint do ciclo agentico de qualidade da Mar.

Fluxo: `make data && make build && make pipeline`.
Modo definido por LLM_MODE (offline por padrao; live chama o Claude).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import orchestrator, profiler            # noqa: E402
from agents.common.llm import LLMClient              # noqa: E402
from agents.common.settings import settings          # noqa: E402
from agents.tools import metrics as metrics_tool     # noqa: E402
from agents.tools.dbt_lineage import Lineage         # noqa: E402
from agents.tools.warehouse import query             # noqa: E402

# Grafo do projeto, usado so se o manifest do dbt ainda nao existir.
FALLBACK_EDGES = {
    "mart_metrics": ["int_transactions_enriched", "stg_marketing"],
    "int_transactions_enriched": ["stg_transactions"],
    "stg_transactions": ["raw_transactions"],
    "stg_marketing": ["raw_marketing_spend"],
    "stg_users": ["raw_users"],
}


def load_lineage() -> Lineage:
    try:
        return Lineage.from_manifest()
    except FileNotFoundError:
        print("(manifest do dbt ausente, usando linhagem de fallback; rode `make build`)\n")
        return Lineage.from_edges(FALLBACK_EDGES)


def main() -> None:
    llm = LLMClient()
    lineage = load_lineage()
    print(f"== Sentinela de Dados · Mar | modo LLM: {settings.llm_mode} ==\n")

    decisions = orchestrator.run(metrics_tool.list_metrics(), lineage, llm)
    print(f"\n{len(decisions)} anomalia(s) processada(s) "
          "(cada uma com causa raiz e correcao proposta, aguardando aprovacao).\n")

    print("== Perfilador: contrato + teste para a fonte raw_transactions ==\n")
    sample = query("select * from raw.raw_transactions order by hash(txn_id) limit 500")
    contract, fix = profiler.profile("raw_transactions", sample, llm)
    print(f"contrato inferido: {len(contract.fields)} campos. "
          f"Correcao proposta -> {fix.target}\n")
    print(fix.content)


if __name__ == "__main__":
    main()
