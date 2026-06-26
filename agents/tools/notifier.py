"""Ferramenta: entrega de alertas. Slack se configurado, senao console.

Espelha o agente de KPIs no Slack ja entregue em producao (case Boticario).
"""
from __future__ import annotations

import json
import urllib.request

from agents.common.settings import settings


def notify(text: str) -> None:
    if settings.slack_webhook:
        req = urllib.request.Request(
            settings.slack_webhook,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)  # noqa: S310
    else:
        print("[notifier:console]\n" + text)
