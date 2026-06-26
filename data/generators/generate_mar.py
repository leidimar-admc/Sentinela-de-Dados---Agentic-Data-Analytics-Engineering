"""Gerador de dados simulados da **Mar** (empresa FICTICIA).

Mar e uma plataforma de cashback e beneficios usada apenas para demonstracao.
Nenhum dado real e utilizado.

O script:
  1. Cria dados operacionais sinteticos (usuarios, parceiros, transacoes, midia).
  2. Injeta ANOMALIAS controladas e grava o *ground truth* em
     `data/anomaly_manifest.json` -> isso permite avaliar os agentes de forma
     objetiva (eixo 4: evals).
  3. Carrega tudo em um arquivo DuckDB (`data/mar.duckdb`) como tabelas `raw_*`,
     que o projeto dbt consome.

E deterministico: mesma SEED -> mesmos dados -> evals reprodutiveis.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------- configuracao
SEED = 42
N_DAYS = 90
N_USERS = 4_000
N_MERCHANTS = 120
# Janela dos ultimos N_DAYS dias, ancorada em hoje, para o historico simulado
# parecer sempre recente. Os VALORES sao deterministicos (SEED); so o calendario
# desliza para acompanhar a data atual.
START = date.today() - timedelta(days=N_DAYS)
CHANNELS = ["email", "google_ads", "facebook_ads", "direct", "organic"]
CATEGORIES = ["mercado", "farmacia", "restaurante", "posto", "vestuario", "viagem"]

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DUCKDB_PATH = ROOT / "data" / "mar.duckdb"
MANIFEST_PATH = ROOT / "data" / "anomaly_manifest.json"


def _days() -> list[date]:
    return [START + timedelta(days=i) for i in range(N_DAYS)]


def _weekly_factor(d: date) -> float:
    # fim de semana movimenta mais uma plataforma de cashback de consumo
    return 1.25 if d.weekday() >= 5 else 1.0


# --------------------------------------------------------------------- tabelas
def make_users(fake: Faker) -> pd.DataFrame:
    rows = []
    for i in range(N_USERS):
        rows.append(
            {
                "user_id": i + 1,
                "signup_date": fake.date_between(START - timedelta(days=365), START),
                "uf": fake.estado_sigla(),
                "segment": random.choices(
                    ["novo", "ativo", "fiel", "hibernando"], weights=[3, 4, 2, 1]
                )[0],
            }
        )
    return pd.DataFrame(rows)


def make_merchants() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "merchant_id": range(1, N_MERCHANTS + 1),
            "category": [random.choice(CATEGORIES) for _ in range(N_MERCHANTS)],
        }
    )


def make_marketing(anomalies: list[dict]) -> pd.DataFrame:
    """Investimento diario por canal. Anomalia A dobra google_ads em uma janela."""
    base = {"email": 6_000, "google_ads": 28_000, "facebook_ads": 22_000,
            "direct": 0, "organic": 0}
    spike = _anom_window(anomalies, "roas")
    rows = []
    for d in _days():
        # investe proporcionalmente ao trafego (acompanha a sazonalidade do GMV),
        # para que o ROAS seja estavel fora da anomalia.
        wf = _weekly_factor(d)
        for ch in CHANNELS:
            spend = base[ch] * wf * np.random.uniform(0.95, 1.05)
            if ch == "google_ads" and spike and spike[0] <= d <= spike[1]:
                spend *= 4.0  # gasto quadruplica, conversao nao acompanha -> ROAS cai
            rows.append({"spend_date": d, "channel": ch, "spend": round(spend, 2)})
    return pd.DataFrame(rows)


def make_transactions(users: pd.DataFrame, merchants: pd.DataFrame,
                      anomalies: list[dict]) -> pd.DataFrame:
    null_w = _anom_window(anomalies, "cashback_null_rate")
    appr_w = _anom_window(anomalies, "approval_rate")
    uids = users["user_id"].to_numpy()
    mids = merchants["merchant_id"].to_numpy()

    rows = []
    txn_id = 0
    for d in _days():
        n = int(np.random.normal(220, 18) * _weekly_factor(d))
        for _ in range(max(n, 0)):
            txn_id += 1
            gmv = float(np.round(np.random.lognormal(mean=4.2, sigma=0.5), 2))
            cashback = round(gmv * np.random.uniform(0.03, 0.08), 2)

            # Anomalia B: buraco de qualidade -> cashback_amount vira NULL
            if null_w and null_w[0] <= d <= null_w[1] and random.random() < 0.35:
                cashback = None

            # Anomalia C: incidente operacional -> cancelamentos disparam
            base_status = ["approved", "cancelled", "refunded"]
            weights = [0.92, 0.05, 0.03]
            if appr_w and appr_w[0] <= d <= appr_w[1]:
                weights = [0.70, 0.27, 0.03]
            status = random.choices(base_status, weights=weights)[0]

            rows.append(
                {
                    "txn_id": txn_id,
                    "txn_ts": f"{d.isoformat()} 12:00:00",
                    "user_id": int(random.choice(uids)),
                    "merchant_id": int(random.choice(mids)),
                    "channel": random.choices(CHANNELS, weights=[2, 3, 3, 1, 1])[0],
                    "gmv": gmv,
                    "cashback_amount": cashback,
                    "status": status,
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- anomalias
def define_anomalies() -> list[dict]:
    """Ground truth: o que foi injetado, onde, e qual no dbt e a causa raiz."""
    d0 = START
    return [
        {
            "id": "A_roas_drop",
            "metric": "roas",
            "type": "level_shift_down",
            "window": [(d0 + timedelta(days=60)).isoformat(),
                       (d0 + timedelta(days=64)).isoformat()],
            "root_cause_node": "stg_marketing",
            "description": "Gasto de google_ads dobrou sem aumento de conversao; "
                           "ROAS total cai. Causa a montante: investimento de midia.",
        },
        {
            "id": "B_cashback_nulls",
            "metric": "cashback_null_rate",
            "type": "spike_up",
            "window": [(d0 + timedelta(days=30)).isoformat(),
                       (d0 + timedelta(days=32)).isoformat()],
            "root_cause_node": "stg_transactions",
            "description": "Falha de captura zera cashback_amount em ~35% das "
                           "transacoes; subnotifica a cashback_liability.",
        },
        {
            "id": "C_approval_drop",
            "metric": "approval_rate",
            "type": "level_shift_down",
            "window": [(d0 + timedelta(days=75)).isoformat(),
                       (d0 + timedelta(days=76)).isoformat()],
            "root_cause_node": "int_transactions_enriched",
            "description": "Incidente no gateway aumenta cancelamentos; a regra de "
                           "status (realizado/perdido) reflete a queda na aprovacao.",
        },
    ]


def _anom_window(anomalies: list[dict], metric: str):
    for a in anomalies:
        if a["metric"] == metric:
            lo, hi = a["window"]
            return date.fromisoformat(lo), date.fromisoformat(hi)
    return None


# ------------------------------------------------------------------------ main
def main() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    fake = Faker("pt_BR")
    Faker.seed(SEED)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    anomalies = define_anomalies()

    users = make_users(fake)
    merchants = make_merchants()
    marketing = make_marketing(anomalies)
    transactions = make_transactions(users, merchants, anomalies)

    tables = {
        "raw_users": users,
        "raw_merchants": merchants,
        "raw_marketing_spend": marketing,
        "raw_transactions": transactions,
    }

    # CSVs (gitignored), uteis para inspecao e para o dbt ler via read_csv_auto
    for name, df in tables.items():
        df.to_csv(RAW_DIR / f"{name}.csv", index=False)

    # carrega no DuckDB que o dbt consome como `source`
    import duckdb

    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    for name, df in tables.items():
        con.register("df_tmp", df)
        con.execute(f"CREATE OR REPLACE TABLE raw.{name} AS SELECT * FROM df_tmp;")
        con.unregister("df_tmp")
    con.close()

    MANIFEST_PATH.write_text(json.dumps(anomalies, indent=2, ensure_ascii=False))

    print(f"OK  usuarios={len(users):,}  parceiros={len(merchants):,}  "
          f"transacoes={len(transactions):,}  dias={N_DAYS}")
    print(f"DuckDB  -> {DUCKDB_PATH.relative_to(ROOT)}")
    print(f"Ground truth ({len(anomalies)} anomalias) -> "
          f"{MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
