from __future__ import annotations

import time

import pytest

from iplanrio_agent_toolkit.rate_limiter import (
    get_rate_limiter,
    initialize_rate_limiter,
    reset_rate_limiter,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


def test_singleton_returns_same_instance() -> None:
    limiter1 = get_rate_limiter(max_concurrent=10, requests_per_minute=100)
    limiter2 = get_rate_limiter(max_concurrent=999, requests_per_minute=999)

    assert limiter1 is limiter2
    # Second call's params are ignored — first construction wins.
    assert limiter1.max_concurrent == 10
    assert limiter1.rpm_limit == 100


def test_initialize_with_force_recreates() -> None:
    initialize_rate_limiter(max_concurrent=5, requests_per_minute=50)
    limiter = initialize_rate_limiter(max_concurrent=20, requests_per_minute=200, force=True)

    assert limiter.max_concurrent == 20
    assert limiter.rpm_limit == 200


def test_acquire_and_release_tracks_current_rate() -> None:
    limiter = get_rate_limiter(max_concurrent=5, requests_per_minute=100)

    assert limiter.get_current_rate() == 0
    limiter.acquire()
    assert limiter.get_current_rate() == 1
    limiter.release()
    # Releasing only frees the concurrency slot; the sliding-window count of
    # requests made in the last 60s is unaffected.
    assert limiter.get_current_rate() == 1


def test_disabled_limiter_is_a_noop() -> None:
    limiter = get_rate_limiter(max_concurrent=1, requests_per_minute=1)
    limiter.set_enabled(False)

    start = time.time()
    for _ in range(10):
        limiter.acquire()
        limiter.release()
    elapsed = time.time() - start

    assert elapsed < 1.0


def test_reset_clears_request_history() -> None:
    limiter = get_rate_limiter(max_concurrent=5, requests_per_minute=100)
    limiter.acquire()
    limiter.release()
    assert limiter.get_current_rate() == 1

    limiter.reset()
    assert limiter.get_current_rate() == 0
