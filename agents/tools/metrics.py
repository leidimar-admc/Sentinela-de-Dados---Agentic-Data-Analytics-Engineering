"""Ferramenta: le a camada de metricas (mart_metrics) como series temporais."""
from __future__ import annotations

import math

from agents.common.schemas import MetricPoint
from agents.tools.warehouse import query


def list_metrics() -> list[str]:
    df = query("select distinct metric_name from mart_metrics order by 1")
    return df["metric_name"].tolist()


def get_series(metric_name: str) -> list[MetricPoint]:
    df = query(
        f"""
        select metric_date, metric_name, metric_value
        from mart_metrics
        where metric_name = '{metric_name}'
        order by metric_date
        """
    )
    out: list[MetricPoint] = []
    for r in df.itertuples(index=False):
        v = r.metric_value
        value = None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
        out.append(MetricPoint(metric_name=r.metric_name, metric_date=r.metric_date,
                               metric_value=value))
    return out
