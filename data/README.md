# Dados simulados da Mar (fictícia)

Gerados por `data/generators/generate_mar.py` (determinístico, `SEED=42`,
90 dias). Nenhum dado real. Saídas (gitignored): CSVs em `data/raw/`, o banco
`data/mar.duckdb` (schema `raw`) e o *ground truth* em `data/anomaly_manifest.json`.

## Esquema (raw)

| Tabela | Campos principais |
| --- | --- |
| `raw_users` | user_id, signup_date, uf, segment |
| `raw_merchants` | merchant_id, category |
| `raw_marketing_spend` | spend_date, channel, spend |
| `raw_transactions` | txn_id, txn_ts, user_id, merchant_id, channel, gmv, cashback_amount, status |

## KPIs (mart_metrics)

`gmv`, `cashback_liability`, `approval_rate`, `cashback_null_rate`,
`active_users`, `roas`, uma linha por métrica/dia.

## Anomalias injetadas (ground truth)

| id | métrica | tipo | causa raiz (nó dbt) |
| --- | --- | --- | --- |
| A | `roas` | queda de nível | `stg_marketing` (gasto de google dobra sem conversão) |
| B | `cashback_null_rate` | pico | `stg_transactions` (falha de captura zera cashback) |
| C | `approval_rate` | queda de nível | `int_transactions_enriched` (incidente no gateway) |

São esses três casos que as **evals** exigem que o Sentinela detecte e diagnostique.
