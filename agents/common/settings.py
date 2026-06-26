"""Configuracao central (lida do ambiente / .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    # modo do LLM: 'offline' (deterministico, CI/sem chave) | 'live' (chama o Claude)
    llm_mode: str = os.getenv("LLM_MODE", "offline")

    # FinOps: modelo barato/rapido para tarefas simples (ex.: inferir contrato),
    # modelo forte so para o raciocinio dificil de causa raiz.
    llm_model_fast: str = os.getenv("LLM_MODEL_FAST", "claude-haiku-4-5")
    llm_model_smart: str = os.getenv("LLM_MODEL_SMART", "claude-sonnet-4-6")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # guardrails do agente
    max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "12"))
    max_usd: float = float(os.getenv("AGENT_MAX_USD", "0.50"))

    slack_webhook: str = os.getenv("SLACK_WEBHOOK_URL", "")

    # observabilidade: arquivo de trace por execucao (opcional)
    trace_file: str = os.getenv("AGENT_TRACE_FILE", "")

    duckdb_path: Path = ROOT / "data" / "mar.duckdb"
    manifest_path: Path = ROOT / "data" / "anomaly_manifest.json"
    dbt_target: Path = ROOT / "transform" / "target"


settings = Settings()
