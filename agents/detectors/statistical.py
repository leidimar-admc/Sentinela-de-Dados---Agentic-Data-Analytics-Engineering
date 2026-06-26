"""Detector ESTATISTICO de anomalias (deterministico).

Separacao deliberada (eixo 4 / rigor): a *deteccao* e estatistica e auditavel;
o LLM entra so depois, para *explicar* e *diagnosticar*. Assim a existencia da
anomalia nao depende do humor do modelo.

Baseline: z-score robusto (mediana + MAD), resistente a outliers. Para series
quase constantes (MAD ~ 0) cai para o desvio padrao classico. O valor e limitado
para nao explodir numericamente. Em producao trocaria por baseline sazonal /
STL, gancho marcado no fim.
"""
from __future__ import annotations

import numpy as np

from agents.common.schemas import AnomalySignal, MetricPoint, Severity

_MAD_TO_SIGMA = 0.6745   # MAD / 0.6745 ~ desvio padrao, para dados ~normais
_Z_CAP = 50.0            # teto do |z| reportado (legibilidade)


def detect(series: list[MetricPoint], z_threshold: float = 3.5,
           min_history: int = 14) -> list[AnomalySignal]:
    pts = [p for p in series if p.metric_value is not None]
    if len(pts) < min_history:
        return []

    values = np.array([p.metric_value for p in pts], dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))

    if mad > 1e-9:
        scale = mad / _MAD_TO_SIGMA
    else:  # serie quase constante -> usa desvio padrao
        scale = float(np.std(values)) or 1e-9

    signals: list[AnomalySignal] = []
    for p, v in zip(pts, values):
        z = float(np.clip((v - median) / scale, -_Z_CAP, _Z_CAP))
        if abs(z) >= z_threshold:
            signals.append(
                AnomalySignal(
                    metric_name=p.metric_name,
                    metric_date=p.metric_date,
                    observed=float(v),
                    expected=median,
                    score=round(z, 2),
                    severity=_severity(abs(z)),
                )
            )
    return signals


def _severity(abs_z: float) -> Severity:
    if abs_z >= 6:
        return Severity.critical
    if abs_z >= 4.5:
        return Severity.warning
    return Severity.info


# Nota de design: a mediana-por-dia-da-semana remove a sazonalidade semanal
# (ex.: gmv sobe no fim de semana) sem o custo de uma decomposicao STL completa.
