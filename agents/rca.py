"""Agente de CAUSA RAIZ (RCA): o Claude navega a linhagem do dbt via tool-use.

Em `live`, o modelo recebe a ferramenta `get_upstream` e a usa para percorrer a
linhagem a partir de `mart_metrics`, decidindo qual no a montante explica a
anomalia; conclui emitindo um `RootCauseHypothesis` validado por Pydantic.

Em `offline`, uma heuristica deterministica (metrica -> no) + a linhagem produzem
a mesma estrutura, para CI/testes.
"""
from __future__ import annotations

import json

from agents.common.llm import LLMClient
from agents.common.schemas import AnomalySignal, RootCauseHypothesis
from agents.tools.dbt_lineage import Lineage

# usado apenas na fixture offline (no modo live quem decide e o Claude)
_OFFLINE_METRIC_TO_NODE = {
    "roas": "stg_marketing",
    "cashback_null_rate": "stg_transactions",
    "cashback_liability": "stg_transactions",
    "approval_rate": "int_transactions_enriched",
    "gmv": "stg_transactions",
    "active_users": "stg_transactions",
}

_SYSTEM = (
    "Voce e engenheiro de analytics fazendo root-cause analysis sobre um projeto "
    "dbt. Use a ferramenta get_upstream para percorrer a linhagem a partir de "
    "'mart_metrics' e identificar o no a montante que melhor explica a anomalia. "
    "Conclua chamando a ferramenta que emite a hipotese, com evidencia objetiva."
)

_GET_UPSTREAM = {
    "name": "get_upstream",
    "description": "Retorna os nos dbt a montante (ancestrais) de um no na linhagem.",
    "input_schema": {
        "type": "object",
        "properties": {"node": {"type": "string",
                                "description": "nome do modelo, ex.: mart_metrics"}},
        "required": ["node"],
    },
}


def diagnose(signal: AnomalySignal, lineage: Lineage, llm: LLMClient) -> RootCauseHypothesis:
    upstream = lineage.upstream("mart_metrics")

    def _offline() -> RootCauseHypothesis:
        suspect = _OFFLINE_METRIC_TO_NODE.get(signal.metric_name, "desconhecido")
        return RootCauseHypothesis(
            metric_name=signal.metric_name,
            metric_date=signal.metric_date,
            suspected_node=suspect,
            evidence=[
                f"mart_metrics depende de {suspect} na linhagem dbt"
                if suspect in upstream else f"no suspeito: {suspect}",
                f"desvio de {signal.score} sigmas em {signal.metric_date}",
            ],
            explanation=(
                f"A anomalia em {signal.metric_name} origina-se provavelmente em "
                f"{suspect}, a montante da camada de metricas."
            ),
            confidence=0.6,
        )

    def _runner(name: str, args: dict) -> str:
        if name == "get_upstream":
            return json.dumps(lineage.upstream(args.get("node", "")))
        return "[]"

    user = (
        f"Anomalia detectada: {signal.model_dump_json()}\n"
        "A metrica vem do mart 'mart_metrics'. Encontre a causa raiz na linhagem."
    )
    hyp = llm.reason(
        system=_SYSTEM, user=user, tools=[_GET_UPSTREAM],
        terminal=RootCauseHypothesis, tool_runner=_runner, offline=_offline, tier="smart",
    )
    # garante que metrica/data refletem o sinal real (nao deixa o modelo trocar)
    return hyp.model_copy(update={"metric_name": signal.metric_name,
                                  "metric_date": signal.metric_date})
