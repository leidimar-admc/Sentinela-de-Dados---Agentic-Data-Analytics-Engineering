from agents.tools.dbt_lineage import Lineage

EDGES = {
    "mart_metrics": ["int_transactions_enriched", "stg_marketing"],
    "int_transactions_enriched": ["stg_transactions"],
    "stg_transactions": ["raw_transactions"],
    "stg_marketing": ["raw_marketing_spend"],
}


def test_transitive_upstream():
    lin = Lineage.from_edges(EDGES)
    up = set(lin.upstream("mart_metrics"))
    assert {"stg_marketing", "stg_transactions", "raw_transactions",
            "raw_marketing_spend", "int_transactions_enriched"} <= up


def test_leaf_has_no_parents():
    lin = Lineage.from_edges(EDGES)
    assert lin.upstream("raw_transactions") == []
