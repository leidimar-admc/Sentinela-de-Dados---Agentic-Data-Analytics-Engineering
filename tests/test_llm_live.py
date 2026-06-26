"""Prova do caminho LIVE sem chave de API.

Simula o transporte da Anthropic (messages.create) para exercitar o codigo real
do modo `live`: o parsing de blocos tool_use, o loop de tool-calling com
tool_result e a contabilizacao de custo. Garante que, quando o Claude responde,
a estrutura e lida e validada corretamente.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import agents.common.llm as llm_mod
from agents import rca
from agents.common.llm import LLMClient
from agents.common.schemas import (AnomalySignal, DataContract,
                                    RootCauseHypothesis, Severity)
from agents.tools.dbt_lineage import Lineage


class _Block:
    """Imita um bloco tool_use da resposta da Anthropic."""

    def __init__(self, name: str, payload: dict, id: str = "tu_1") -> None:
        self.type = "tool_use"
        self.name = name
        self.input = payload
        self.id = id


class _Resp:
    def __init__(self, blocks: list[_Block]) -> None:
        self.content = blocks
        self.stop_reason = "tool_use"
        self.usage = SimpleNamespace(input_tokens=120, output_tokens=60)


class _Messages:
    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.calls = 0

    def create(self, **_kwargs) -> _Resp:
        resp = self._scripted[self.calls]
        self.calls += 1
        return resp


class _FakeAnthropic:
    def __init__(self, scripted: list[_Resp]) -> None:
        self.messages = _Messages(scripted)


@pytest.fixture
def live(monkeypatch):
    """Coloca o cliente em modo live com settings falsos (sem chave real)."""
    fake = SimpleNamespace(llm_mode="live", llm_model_fast="haiku-test",
                           llm_model_smart="sonnet-test",
                           anthropic_api_key="x", max_usd=10.0)
    monkeypatch.setattr(llm_mod, "settings", fake)
    return fake


def test_structured_parses_tool_use(live):
    """structured(): le o bloco tool_use e devolve o schema validado."""
    client = LLMClient()
    payload = {"model": "raw_x", "fields": [
        {"name": "id", "data_type": "bigint", "not_null": True, "accepted_values": None},
        {"name": "status", "data_type": "varchar", "not_null": True,
         "accepted_values": ["a", "b"]}]}
    fake = _FakeAnthropic([_Resp([_Block("emit", payload)])])
    client._anthropic = lambda: fake

    out = client.structured(system="s", user="u", schema=DataContract,
                            offline=lambda: pytest.fail("nao deveria usar o offline"))

    assert isinstance(out, DataContract)
    assert out.model == "raw_x"
    assert out.fields[1].accepted_values == ["a", "b"]
    assert fake.messages.calls == 1                        # chamou a API uma vez
    assert client.calls == 1 and client.spent_usd > 0     # custo foi contabilizado


def test_reason_runs_tool_loop_then_concludes(live):
    """reason(): Claude chama get_upstream, recebe o tool_result e conclui."""
    client = LLMClient()
    lineage = Lineage.from_edges({"mart_metrics": ["stg_marketing"],
                                  "stg_marketing": ["raw_marketing_spend"]})
    hypothesis = {"metric_name": "roas", "metric_date": "2025-03-02",
                  "suspected_node": "stg_marketing", "evidence": ["gasto dobrou"],
                  "explanation": "causa a montante em stg_marketing", "confidence": 0.7}
    fake = _FakeAnthropic([
        _Resp([_Block("get_upstream", {"node": "mart_metrics"})]),   # 1a volta: usa a tool
        _Resp([_Block("conclude", hypothesis)]),                     # 2a volta: conclui
    ])
    client._anthropic = lambda: fake

    signal = AnomalySignal(metric_name="roas", metric_date=date(2025, 3, 2),
                           observed=0.1, expected=0.3, score=-6.0,
                           severity=Severity.critical)
    out = rca.diagnose(signal, lineage, client)

    assert isinstance(out, RootCauseHypothesis)
    assert out.suspected_node == "stg_marketing"
    assert out.metric_name == "roas"                       # ancorado no sinal real
    assert fake.messages.calls == 2                        # rodou o loop: tool -> conclude
    assert client.calls == 2
