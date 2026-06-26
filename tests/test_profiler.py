import pandas as pd

from agents.common.llm import LLMClient
from agents.common.schemas import FixKind
from agents import profiler


def test_profiler_infers_contract_and_test():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "status": ["approved", "cancelled", "approved"],
        "amount": [10.0, 20.0, None],
    })
    contract, fix = profiler.profile("raw_demo", df, LLMClient())
    fields = {f.name: f for f in contract.fields}
    assert fields["id"].not_null is True
    assert fields["amount"].not_null is False           # tem nulo
    assert fields["status"].accepted_values == ["approved", "cancelled"]
    assert fix.kind == FixKind.dbt_test
