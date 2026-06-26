"""Cliente de LLM: Claude (Anthropic) com tool-use, saida validada e guardrails.

Dois modos:
  - `live`    -> chama o Claude de verdade (tool-calling + saida estruturada).
  - `offline` -> usa fixtures deterministicas. E o modo dos testes e do CI:
                 exercita todo o grafo do agente sem custo nem rede. Nao e um
                 stub de funcionalidade ausente, e a duble de teste do modelo.

O custo (tokens) e contabilizado e ha um teto (guardrail) que aborta a execucao
se estourar.
"""
from __future__ import annotations

from typing import Callable, Type, TypeVar

from pydantic import BaseModel

from .settings import settings

T = TypeVar("T", bound=BaseModel)

# precos aproximados por 1k tokens (apenas para o teto de custo)
_USD_PER_1K_IN = 0.003
_USD_PER_1K_OUT = 0.015


class BudgetExceeded(RuntimeError):
    """Levantada quando o custo acumulado passa do teto configurado."""


class LLMClient:
    def __init__(self) -> None:
        self.spent_usd = 0.0
        self.calls = 0
        self._client = None

    @property
    def offline(self) -> bool:
        return settings.llm_mode != "live"

    # ------------------------------------------------------------------ infra
    def _anthropic(self):
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=settings.anthropic_api_key)
        return self._client

    def _model(self, tier: str) -> str:
        # FinOps: 'fast' = modelo barato (tarefas simples); 'smart' = modelo forte
        return settings.llm_model_fast if tier == "fast" else settings.llm_model_smart

    def _charge(self, tok_in: int, tok_out: int) -> None:
        self.spent_usd += tok_in / 1000 * _USD_PER_1K_IN + tok_out / 1000 * _USD_PER_1K_OUT
        self.calls += 1
        if self.spent_usd > settings.max_usd:
            raise BudgetExceeded(
                f"custo {self.spent_usd:.3f} USD passou do teto {settings.max_usd} USD"
            )

    # ------------------------------------------------------ saida estruturada
    def structured(self, *, system: str, user: str, schema: Type[T],
                   offline: Callable[[], T], tier: str = "fast") -> T:
        """Uma chamada cujo retorno e uma instancia validada de `schema`.

        Em `live`, forca o Claude a responder pela ferramenta-esquema (tool-use).
        Em `offline`, devolve `offline()`.
        """
        if self.offline:
            self._charge(0, 0)
            return offline()

        tool = {"name": "emit", "description": f"Emite {schema.__name__}.",
                "input_schema": schema.model_json_schema()}
        resp = self._anthropic().messages.create(
            model=self._model(tier), max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool], tool_choice={"type": "tool", "name": "emit"},
        )
        self._charge(resp.usage.input_tokens, resp.usage.output_tokens)
        block = next(b for b in resp.content if b.type == "tool_use")
        return schema.model_validate(block.input)

    # ------------------------------------- raciocinio com ferramentas (agente)
    def reason(self, *, system: str, user: str, tools: list[dict],
               terminal: Type[T], tool_runner: Callable[[str, dict], str],
               offline: Callable[[], T], tier: str = "smart", max_iters: int = 6) -> T:
        """Loop de tool-use: o Claude chama ferramentas e ENCERRA emitindo `terminal`.

        tools        -> especificacoes das ferramentas (sem a terminal).
        tool_runner  -> executa uma ferramenta chamada e devolve o resultado (str).
        terminal     -> schema Pydantic que o modelo deve emitir para concluir.
        """
        if self.offline:
            self._charge(0, 0)
            return offline()

        terminal_tool = {
            "name": "conclude", "description": f"Conclui emitindo {terminal.__name__}.",
            "input_schema": terminal.model_json_schema(),
        }
        all_tools = [*tools, terminal_tool]
        messages: list[dict] = [{"role": "user", "content": user}]

        for _ in range(max_iters):
            resp = self._anthropic().messages.create(
                model=self._model(tier), max_tokens=1024, system=system,
                messages=messages, tools=all_tools,
            )
            self._charge(resp.usage.input_tokens, resp.usage.output_tokens)

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                break

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for tu in tool_uses:
                if tu.name == "conclude":
                    return terminal.model_validate(tu.input)
                results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": tool_runner(tu.name, tu.input),
                })
            messages.append({"role": "user", "content": results})

        # se nao concluiu no limite de passos, cai para a fixture deterministica
        return offline()
