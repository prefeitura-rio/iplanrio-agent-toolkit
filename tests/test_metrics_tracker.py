from __future__ import annotations

from iplanrio_agent_toolkit.metrics_tracker import APIMetricsTracker


def test_empty_tracker_returns_zeroed_metrics() -> None:
    tracker = APIMetricsTracker()
    tracker.reset()

    metrics = tracker.get_metrics()

    assert metrics.total_calls == 0
    assert metrics.by_type == {}
    assert metrics.error_429_count == 0


def test_records_calls_grouped_by_arbitrary_type() -> None:
    tracker = APIMetricsTracker()
    tracker.reset()

    tracker.record_call(api_type="classification", duration_ms=100, success=True)
    tracker.record_call(api_type="classification", duration_ms=200, success=True)
    tracker.record_call(api_type="extraction", duration_ms=300, success=True)
    tracker.record_call(api_type="some_other_kind", duration_ms=50, success=True)

    metrics = tracker.get_metrics()

    assert metrics.total_calls == 4
    assert set(metrics.by_type) == {"classification", "extraction", "some_other_kind"}
    assert metrics.by_type["classification"].total == 2
    assert metrics.by_type["extraction"].total == 1


def test_tracks_429_errors_separately() -> None:
    tracker = APIMetricsTracker()
    tracker.reset()

    tracker.record_call(api_type="extraction", duration_ms=100, success=False, error_type="429 Resource Exhausted")
    tracker.record_call(api_type="extraction", duration_ms=100, success=False, error_type="500 Internal Error")

    metrics = tracker.get_metrics()

    assert metrics.error_429_count == 1
    assert metrics.other_api_errors == 1


def test_percentile_and_max_concurrent_are_computed() -> None:
    tracker = APIMetricsTracker()
    tracker.reset()

    for duration in [10, 20, 30, 40, 50]:
        tracker.record_call(api_type="x", duration_ms=duration, success=True)

    metrics = tracker.get_metrics()
    type_metrics = metrics.by_type["x"]

    assert type_metrics.p50_ms == 30
    assert type_metrics.max_concurrent >= 1
