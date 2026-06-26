"""Ferramenta: executa SQL no DuckDB e devolve um DataFrame."""
from __future__ import annotations

import duckdb
import pandas as pd

from agents.common.settings import settings


def query(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        return con.execute(sql).fetch_df()
    finally:
        con.close()
