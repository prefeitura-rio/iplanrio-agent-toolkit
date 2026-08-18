"""Global, thread-safe rate limiter for outbound API calls.

Controls two independent limits:

- Max concurrent requests in flight (semaphore).
- Requests per minute, using a sliding window (deque of timestamps).

Usage::

    limiter = get_rate_limiter(max_concurrent=50, requests_per_minute=600)
    limiter.acquire()
    try:
        response = api_call()
    finally:
        limiter.release()
"""

from __future__ import annotations

import threading
import time
from collections import deque

from iplanrio_agent_toolkit.logging import get_logger

logger = get_logger(__name__)

_RPM_WINDOW_SECONDS = 60


class GlobalRateLimiter:
    """Process-wide singleton rate limiter combining a concurrency semaphore with a sliding-window RPM limit."""

    _instance: GlobalRateLimiter | None = None
    _lock = threading.Lock()

    def __new__(cls, max_concurrent: int = 50, requests_per_minute: int = 600) -> GlobalRateLimiter:  # noqa: ARG004 - mirrors __init__ signature
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_concurrent: int = 50, requests_per_minute: int = 600) -> None:
        """Initialize the singleton on first construction; ignore later re-configuration attempts.

        :param max_concurrent: Maximum number of requests allowed in flight simultaneously.
        :param requests_per_minute: Maximum number of requests allowed per rolling 60s window.
        """
        if self._initialized:
            if self.max_concurrent != max_concurrent or self.rpm_limit != requests_per_minute:
                logger.warning(
                    "[RateLimiter] Attempting to reconfigure singleton from (%s, %s) to (%s, %s). "
                    "Using existing configuration.",
                    self.max_concurrent,
                    self.rpm_limit,
                    max_concurrent,
                    requests_per_minute,
                )
            return

        self.max_concurrent = max_concurrent
        self.rpm_limit = requests_per_minute
        self.enabled = True  # can be disabled for tests

        self.semaphore = threading.Semaphore(max_concurrent)
        self.request_times: deque[float] = deque()
        self.times_lock = threading.Lock()

        self._initialized = True

        logger.info(
            "[RateLimiter] Initialized with max_concurrent=%s, rpm=%s (%.1f RPS)",
            max_concurrent,
            requests_per_minute,
            requests_per_minute / 60,
        )

    def acquire(self) -> None:
        """Acquire permission to make a request, blocking until both limits allow it."""
        if not self.enabled:
            return

        self.semaphore.acquire()
        self._wait_for_rpm_limit()

        # Recorded here (after the concurrency slot is acquired, before the
        # API call starts) so the sliding window also reflects in-flight
        # requests, not just completed ones.
        with self.times_lock:
            self.request_times.append(time.time())

    def release(self) -> None:
        """Release the concurrency slot after a request completes."""
        if not self.enabled:
            return
        self.semaphore.release()

    def _wait_for_rpm_limit(self) -> None:
        """Block until the sliding-window requests-per-minute limit allows another request."""
        while True:
            with self.times_lock:
                now = time.time()
                while self.request_times and now - self.request_times[0] > _RPM_WINDOW_SECONDS:
                    self.request_times.popleft()

                if len(self.request_times) < self.rpm_limit:
                    return

                oldest_request = self.request_times[0]
                wait_time = 60 - (now - oldest_request)

            if wait_time > 0:
                time.sleep(min(wait_time, 0.1))
            else:
                time.sleep(0.01)

    def get_current_rate(self) -> float:
        """Return the number of requests recorded in the last 60 seconds.

        :returns: Count of requests in the current sliding window.
        """
        with self.times_lock:
            now = time.time()
            while self.request_times and now - self.request_times[0] > _RPM_WINDOW_SECONDS:
                self.request_times.popleft()
            return len(self.request_times)

    def get_current_rps(self) -> float:
        """Return the average requests-per-second over the last 60 seconds.

        :returns: Average RPS in the current sliding window.
        """
        return self.get_current_rate() / 60.0

    def reset(self) -> None:
        """Clear the sliding window (intended for use in tests)."""
        with self.times_lock:
            self.request_times.clear()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable rate limiting entirely.

        :param enabled: If ``False``, ``acquire``/``release`` become no-ops.
        """
        self.enabled = enabled
        if enabled:
            logger.info("[RateLimiter] Enabled")
        else:
            logger.warning("[RateLimiter] Disabled - no rate limiting applied")


_rate_limiter: GlobalRateLimiter | None = None
_limiter_lock = threading.Lock()


def get_rate_limiter(max_concurrent: int = 50, requests_per_minute: int = 600) -> GlobalRateLimiter:
    """Get or lazily create the global rate limiter singleton.

    :param max_concurrent: Maximum concurrent API requests, used only on first creation.
    :param requests_per_minute: Maximum requests per minute, used only on first creation.
    :returns: The process-wide :class:`GlobalRateLimiter` instance.
    """
    global _rate_limiter  # noqa: PLW0603 - module-level singleton holder
    if _rate_limiter is None:
        with _limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = GlobalRateLimiter(max_concurrent, requests_per_minute)
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Drop the global rate limiter singleton (intended for use in tests)."""
    global _rate_limiter  # noqa: PLW0603 - module-level singleton holder
    with _limiter_lock:
        _rate_limiter = None
        GlobalRateLimiter._instance = None


def initialize_rate_limiter(
    max_concurrent: int = 50,
    requests_per_minute: int = 600,
    force: bool = False,
) -> GlobalRateLimiter:
    """Initialize the global rate limiter with specific parameters.

    Must be called before any other code acquires the singleton via
    :func:`get_rate_limiter`, since the singleton ignores later
    reconfiguration attempts.

    :param max_concurrent: Maximum concurrent API requests.
    :param requests_per_minute: Maximum requests per minute.
    :param force: If ``True``, reset and recreate the singleton with the new parameters.
    :returns: The process-wide :class:`GlobalRateLimiter` instance.
    """
    global _rate_limiter  # noqa: PLW0603 - module-level singleton holder

    if force and _rate_limiter is not None:
        logger.warning("[RateLimiter] Forcing reset and recreation with new parameters")
        reset_rate_limiter()

    with _limiter_lock:
        if _rate_limiter is None:
            _rate_limiter = GlobalRateLimiter(max_concurrent, requests_per_minute)
        elif _rate_limiter.max_concurrent != max_concurrent or _rate_limiter.rpm_limit != requests_per_minute:
            logger.error(
                "[RateLimiter] Rate limiter already initialized with different params! "
                "Existing: max_concurrent=%s, rpm=%s. Requested: max_concurrent=%s, rpm=%s. "
                "Using existing configuration. Call initialize_rate_limiter() BEFORE importing any modules!",
                _rate_limiter.max_concurrent,
                _rate_limiter.rpm_limit,
                max_concurrent,
                requests_per_minute,
            )

    return _rate_limiter
