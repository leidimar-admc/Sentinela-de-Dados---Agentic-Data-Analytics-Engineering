"""Ferramenta: leitura da LINHAGEM do projeto dbt (manifest.json).

E isto que ancora o RCA na engenharia de verdade (eixo 3): em vez de o LLM
"chutar" a causa, ele percorre o grafo de dependencias que o proprio dbt gera
(manifest.json), no nivel de modelo.
"""
from __future__ import annotations

import json
from pathlib import Path

from agents.common.settings import settings


class Lineage:
    def __init__(self, child_to_parents: dict[str, list[str]]) -> None:
        self._parents = child_to_parents

    @classmethod
    def from_manifest(cls, manifest_path: Path | None = None) -> "Lineage":
        path = Path(manifest_path or (settings.dbt_target / "manifest.json"))
        if not path.exists():
            raise FileNotFoundError(
                f"manifest dbt nao encontrado em {path}. Rode `make build` antes."
            )
        manifest = json.loads(path.read_text())
        edges: dict[str, list[str]] = {}
        for unique_id, node in manifest.get("nodes", {}).items():
            edges[_short(unique_id)] = [
                _short(p) for p in node.get("depends_on", {}).get("nodes", [])
            ]
        return cls(edges)

    @classmethod
    def from_edges(cls, edges: dict[str, list[str]]) -> "Lineage":
        """Util para testes (sem precisar de um projeto dbt buildado)."""
        return cls(edges)

    def upstream(self, node: str) -> list[str]:
        """Todos os ancestrais de `node` (busca transitiva)."""
        seen: list[str] = []
        stack = list(self._parents.get(node, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.append(cur)
            stack.extend(self._parents.get(cur, []))
        return seen

    def nodes(self) -> list[str]:
        return list(self._parents.keys())


def _short(unique_id: str) -> str:
    # 'model.mar.stg_marketing' -> 'stg_marketing'
    # 'source.mar.raw.raw_marketing_spend' -> 'raw_marketing_spend'
    return unique_id.split(".")[-1]

