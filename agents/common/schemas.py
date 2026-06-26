"""Contratos (Pydantic) trocados entre agentes e ferramentas.

Toda saida de tool e de agente passa por um destes schemas. Isso e o que
transforma "um prompt gigante" em um sistema com interfaces validadas (eixo 2):
o LLM pode errar o conteudo, mas nunca o *formato*, se nao validar, falha cedo.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class MetricPoint(BaseModel):
    metric_name: str
    metric_date: date
    metric_value: float | None


class AnomalySignal(BaseModel):
    """Saida do detector estatistico (deterministico)."""
    metric_name: str
    metric_date: date
    observed: float
    expected: float
    score: float = Field(description="z-score robusto (desvios da mediana via MAD)")
    severity: Severity
    method: str = "robust_zscore"


class RootCauseHypothesis(BaseModel):
    """Saida do agente de RCA. Causa raiz ancorada na linhagem dbt."""
    metric_name: str
    metric_date: date
    suspected_node: str = Field(description="no dbt suspeito, ex.: 'stg_marketing'")
    evidence: list[str] = Field(default_factory=list)
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)


class FixKind(str, Enum):
    dbt_test = "dbt_test"
    sql_patch = "sql_patch"
    doc = "doc"


class ProposedFix(BaseModel):
    """Proposta do agente. NUNCA aplicada sozinha, vira PR para revisao humana."""
    kind: FixKind
    target: str = Field(description="arquivo/modelo alvo, ex.: 'models/staging/stg_transactions.sql'")
    content: str = Field(description="conteudo do teste/patch/doc proposto")
    rationale: str
    requires_human_approval: Literal[True] = True


class ContractField(BaseModel):
    name: str
    data_type: str
    not_null: bool = False
    accepted_values: list[str] | None = None


class DataContract(BaseModel):
    """Saida do agente perfilador para uma fonte nova."""
    model: str
    fields: list[ContractField]


class AgentDecision(BaseModel):
    """Estado final de um ciclo do orquestrador (o que vira o PR/alerta)."""
    signal: AnomalySignal
    hypothesis: RootCauseHypothesis | None = None
    fix: ProposedFix | None = None
    approved_by_human: bool = False
