from datetime import date, timedelta

from agents.common.schemas import MetricPoint
from agents.detectors import statistical


def _series(values):
    d0 = date(2025, 1, 1)
    return [MetricPoint(metric_name="m", metric_date=d0 + timedelta(days=i),
                        metric_value=v) for i, v in enumerate(values)]


def test_flags_clear_spike():
    values = [100.0] * 30
    values[20] = 400.0  # spike
    signals = statistical.detect(_series(values))
    assert any(s.metric_date == date(2025, 1, 21) for s in signals)


def test_quiet_series_has_no_anomaly():
    import random
    random.seed(0)
    values = [100.0 + random.uniform(-1, 1) for _ in range(40)]
    assert statistical.detect(_series(values)) == []


def test_short_series_returns_empty():
    assert statistical.detect(_series([1.0, 2.0, 3.0])) == []
