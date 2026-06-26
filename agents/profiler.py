"""Agente PERFILADOR: dada uma fonte nova, infere o data contract e gera testes.

Em `live`, o Claude infere o contrato a partir de uma amostra (saida validada como
`DataContract`). Em `offline`, inferimos por dtype. Em ambos, o contrato vira um
`ProposedFix` com o YAML de testes do dbt, que abre PR, nunca aplica sozinho.
"""
from __future__ import annotations

import pandas as pd

from agents.common.llm import LLMClient
from agents.common.schemas import ContractField, DataContract, FixKind, ProposedFix

_SYSTEM = (
    "Voce infere contratos de dados a partir de uma amostra. Para cada coluna, "
    "defina tipo, se e nao-nula e (quando for dominio pequeno e categorico) os "
    "valores aceitos. Nao trate datas/timestamps como categoricos."
)


def profile(model: str, sample: pd.DataFrame, llm: LLMClient) -> tuple[DataContract, ProposedFix]:
    def _offline() -> DataContract:
        fields: list[ContractField] = []
        for col in sample.columns:
            s = sample[col]
            accepted = None
            categorical = not (pd.api.types.is_numeric_dtype(s)
                               or pd.api.types.is_bool_dtype(s)
                               or pd.api.types.is_datetime64_any_dtype(s)
                               or _looks_temporal(s))
            if categorical and s.nunique(dropna=True) <= 6:
                accepted = sorted(map(str, s.dropna().unique()))
            fields.append(ContractField(
                name=col, data_type=_dtype(s),
                not_null=bool(s.notna().all()), accepted_values=accepted))
        return DataContract(model=model, fields=fields)

    user = f"Amostra de {model} (CSV):\n{sample.head(30).to_csv(index=False)}"
    contract = llm.structured(system=_SYSTEM, user=user, schema=DataContract, offline=_offline, tier="fast")

    fix = ProposedFix(
        kind=FixKind.dbt_test,
        target=f"models/staging/_{model}.yml",
        content=_to_dbt_yaml(contract),
        rationale="Garante schema/dominio da fonte a cada build (data contract).",
    )
    return contract, fix


def _looks_temporal(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    sample = s.dropna().astype(str).head(5)
    return any(("-" in v and ":" in v) or v.count("-") == 2 for v in sample)


def _dtype(s: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(s):
        return "bigint"
    if pd.api.types.is_float_dtype(s):
        return "double"
    if pd.api.types.is_datetime64_any_dtype(s) or _looks_temporal(s):
        return "timestamp"
    return "varchar"


def _to_dbt_yaml(c: DataContract) -> str:
    lines = ["version: 2", "", "models:", f"  - name: {c.model}", "    columns:"]
    for f in c.fields:
        lines.append(f"      - name: {f.name}")
        tests = ["not_null"] if f.not_null else []
        if tests or f.accepted_values:
            lines.append("        tests:")
            for t in tests:
                lines.append(f"          - {t}")
            if f.accepted_values:
                vals = ", ".join(f"'{v}'" for v in f.accepted_values)
                lines.append("          - accepted_values:")
                lines.append(f"              values: [{vals}]")
    return "\n".join(lines) + "\n"
