"""Orquestrador do ciclo agentico, um grafo LangGraph com human-in-the-loop.

Para cada anomalia escalada, roda um StateGraph:

    diagnose (Claude + linhagem) -> propose_fix (Claude) -> [PAUSA] -> open_pr

O grafo PAUSA antes de `open_pr` (interrupt do LangGraph): o agente propoe, um
humano aprova, e so entao o PR e aberto. Nada muta producao sozinho. Os guardrails
sao o recursion_limit do grafo e o teto de custo no cliente de LLM.

A deteccao e estatistica e deterministica (de proposito); o LLM raciocina sobre a
causa e a correcao. O modo `offline` roda este MESMO grafo sem chamar o modelo.

O estado do grafo trafega como dicts JSON (serializaveis pelo checkpointer); os
objetos Pydantic sao reconstruidos nas bordas.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents import rca, sentinel
from agents.common.llm import LLMClient
from agents.common.schemas import (AgentDecision, AnomalySignal, FixKind,
                                    ProposedFix, RootCauseHypothesis)
from agents.common.settings import settings
from agents.detectors import statistical
from agents.tools import metrics as metrics_tool
from agents.tools import notifier
from agents.tools.dbt_lineage import Lineage
from observability import tracing


class _State(TypedDict, total=False):
    signal: dict
    hypothesis: dict
    fix: dict
    pr_opened: bool


def _propose_fix(signal: AnomalySignal, hypothesis: RootCauseHypothesis) -> ProposedFix:
    metric = signal.metric_name
    content = (
        f"-- tests/assert_{metric}_within_bounds.sql  (PROPOSTO)\n"
        f"-- Monitora '{metric}'. Origem provavel: {hypothesis.suspected_node}.\n"
        "select metric_date, metric_value\n"
        "from {{ ref('mart_metrics') }}\n"
        f"where metric_name = '{metric}'\n"
        "-- limites parametrizaveis (ex.: z robusto > 3.5)\n"
    )
    return ProposedFix(
        kind=FixKind.dbt_test, target="tests/", content=content,
        rationale=f"Teste de monitoramento que teria pego a anomalia em {metric}.")


def build_graph(lineage: Lineage, llm: LLMClient):
    def diagnose(state: _State) -> _State:
        with tracing.span("diagnose"):
            signal = AnomalySignal.model_validate(state["signal"])
            hyp = rca.diagnose(signal, lineage, llm)
            return {"hypothesis": hyp.model_dump(mode="json")}

    def propose_fix(state: _State) -> _State:
        with tracing.span("propose_fix"):
            signal = AnomalySignal.model_validate(state["signal"])
            hyp = RootCauseHypothesis.model_validate(state["hypothesis"])
            return {"fix": _propose_fix(signal, hyp).model_dump(mode="json")}

    def open_pr(state: _State) -> _State:
        with tracing.span("open_pr"):
            # producao: abrir PR via API do GitHub. Aqui: marca como aberto.
            return {"pr_opened": True}

    g = StateGraph(_State)
    g.add_node("diagnose", diagnose)
    g.add_node("propose_fix", propose_fix)
    g.add_node("open_pr", open_pr)
    g.add_edge(START, "diagnose")
    g.add_edge("diagnose", "propose_fix")
    g.add_edge("propose_fix", "open_pr")
    g.add_edge("open_pr", END)
    # interrupt_before -> human-in-the-loop: pausa antes de abrir o PR
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["open_pr"])


def run(metric_names: list[str], lineage: Lineage, llm: LLMClient | None = None,
        auto_approve: bool = False) -> list[AgentDecision]:
    llm = llm or LLMClient()
    graph = build_graph(lineage, llm)
    tracing.STORE.reset()
    decisions: list[AgentDecision] = []

    for name in metric_names:
        for signal in sentinel.escalate(statistical.detect(metrics_tool.get_series(name))):
            cfg = {"configurable": {"thread_id": f"{signal.metric_name}-{signal.metric_date}"},
                   "recursion_limit": settings.max_steps}
            values = graph.invoke({"signal": signal.model_dump(mode="json")}, cfg)
            decision = AgentDecision(
                signal=signal,
                hypothesis=RootCauseHypothesis.model_validate(values["hypothesis"]),
                fix=ProposedFix.model_validate(values["fix"]),
            )
            if auto_approve:
                graph.invoke(None, cfg)            # humano aprova -> open_pr
                decision.approved_by_human = True
            _alert(decision)
            decisions.append(decision)

    tracing.emit("sentinela", llm)
    return decisions


def _alert(decision: AgentDecision) -> None:
    s, h = decision.signal, decision.hypothesis
    status = "PR aberto (simulado)" if decision.approved_by_human else \
        "aguardando aprovacao humana (PR)"
    notifier.notify(
        "🔎 *Sentinela de Dados · Mar*\n" + sentinel.explain(s)
        + f"\n• causa provavel: `{h.suspected_node}` (confianca {h.confidence:.0%})"
        + f"\n• proposta: {decision.fix.kind.value} → {status}")
