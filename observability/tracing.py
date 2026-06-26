"""Observabilidade dos agentes (eixo 4): spans de latencia + tokens + custo.

Cada execucao do orquestrador produz um trace: a duracao de cada no do grafo, o
numero de chamadas ao LLM e o custo. Defina AGENT_TRACE_FILE para gravar em JSON.
"""
from __future__ import annotations

import contextlib
import functools
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from agents.common.settings import settings


@dataclass
class TraceStore:
    spans: list[dict] = field(default_factory=list)

    def record(self, name: str, ms: float) -> None:
        self.spans.append({"span": name, "ms": round(ms, 1)})

    def reset(self) -> None:
        self.spans.clear()


STORE = TraceStore()


@contextlib.contextmanager
def span(name: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        STORE.record(name, (time.perf_counter() - t0) * 1000)


def traced(name: str):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with span(name):
                return fn(*args, **kwargs)
        return wrapper
    return deco


def emit(run: str, llm=None, store: TraceStore = STORE) -> dict:
    trace = {
        "run": run,
        "total_ms": round(sum(s["ms"] for s in store.spans), 1),
        "llm_calls": getattr(llm, "calls", 0),
        "usd": round(getattr(llm, "spent_usd", 0.0), 4),
        "spans": list(store.spans),
    }
    print(f"[trace] {run}: {trace['total_ms']}ms | "
          f"{trace['llm_calls']} chamada(s) LLM | ${trace['usd']}")
    if settings.trace_file:
        Path(settings.trace_file).write_text(json.dumps(trace, indent=2, default=str))
    return trace
