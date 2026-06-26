"""Agente SENTINELA: triagem das anomalias detectadas.

Recebe os sinais do detector estatistico e decide o que escalar, por severidade,
de forma deterministica. Em modo live, o LLM pode ainda suprimir falso-positivo
conhecido (ex.: pico sazonal esperado) e enriquecer a explicacao.
"""
from __future__ import annotations

from agents.common.schemas import AnomalySignal, Severity


def escalate(signals: list[AnomalySignal]) -> list[AnomalySignal]:
    return [s for s in signals if s.severity != Severity.info]


def explain(signal: AnomalySignal) -> str:
    direction = "acima" if signal.observed > signal.expected else "abaixo"
    return (
        f"{signal.metric_name} em {signal.metric_date} ficou {direction} do "
        f"esperado: observado={signal.observed:.4g} vs baseline={signal.expected:.4g} "
        f"(z={signal.score}, severidade={signal.severity.value})."
    )
