"""Thread-safe tracker for API call metrics (rate, latency, concurrency, errors).

Tracks calls grouped by an arbitrary ``api_type`` label (e.g. ``"classification"``,
``"extraction"``, or anything else the caller chooses) so it stays useful for
any pipeline that makes more than one kind of outbound API call.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class APICallRecord:
    """Record of a single API call."""

    timestamp: float
    api_type: str
    duration_ms: float
    success: bool = True
    error_type: str | None = None
    thread_id: int = 0


@dataclass
class TypeMetrics:
    """Metrics computed for a single ``api_type``."""

    total: int = 0
    rps_mean: float = 0.0
    rps_peak: float = 0.0
    rpm_mean: float = 0.0
    rpm_peak: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_concurrent: int = 0


@dataclass
class Metrics:
    """Aggregate metrics snapshot returned by :meth:`APIMetricsTracker.get_metrics`."""

    total_calls: int = 0
    by_type: dict[str, TypeMetrics] = field(default_factory=dict)
    error_429_count: int = 0
    error_429_first_timestamp: float | None = None
    error_429_rate_when_occurred: dict[str, float] = field(default_factory=dict)
    other_api_errors: int = 0
    max_concurrent_total: int = 0


class APIMetricsTracker:
    """Process-wide singleton tracker for outbound API call metrics."""

    _instance: APIMetricsTracker | None = None
    _lock = threading.Lock()

    def __new__(cls) -> APIMetricsTracker:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize tracking state on first construction; no-op on subsequent calls."""
        if self._initialized:
            return

        self._data_lock = threading.Lock()
        self.records: list[APICallRecord] = []
        self.errors_429: list[APICallRecord] = []
        self.start_time = time.time()
        self._initialized = True

    def record_call(
        self,
        api_type: str,
        duration_ms: float,
        success: bool = True,
        error_type: str | None = None,
    ) -> None:
        """Record a single completed API call.

        :param api_type: Free-form label identifying the kind of call (e.g. ``"classification"``).
        :param duration_ms: Wall-clock duration of the call, in milliseconds.
        :param success: Whether the call succeeded.
        :param error_type: Error message/type when ``success`` is ``False``.
        """
        record = APICallRecord(
            timestamp=time.time(),
            api_type=api_type,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            thread_id=threading.current_thread().ident or 0,
        )

        with self._data_lock:
            self.records.append(record)
            if error_type and "429" in str(error_type):
                self.errors_429.append(record)

    def get_metrics(self) -> Metrics:
        """Compute and return a snapshot of all tracked metrics.

        :returns: A :class:`Metrics` object, empty if no calls were recorded yet.
        """
        with self._data_lock:
            if not self.records:
                return Metrics()

            total_duration = time.time() - self.start_time
            api_types = {r.api_type for r in self.records}

            by_type = {
                api_type: self._type_metrics(
                    [r for r in self.records if r.api_type == api_type],
                    total_duration,
                )
                for api_type in api_types
            }

            other_errors = len(
                [r for r in self.records if not r.success and r.error_type and "429" not in str(r.error_type)]
            )

            return Metrics(
                total_calls=len(self.records),
                by_type=by_type,
                error_429_count=len(self.errors_429),
                error_429_first_timestamp=(self.errors_429[0].timestamp if self.errors_429 else None),
                error_429_rate_when_occurred=self._get_rate_at_first_429(),
                other_api_errors=other_errors,
                max_concurrent_total=self._calculate_max_concurrent(self.records),
            )

    def _type_metrics(self, records: list[APICallRecord], total_duration: float) -> TypeMetrics:
        rps_mean = len(records) / total_duration if total_duration > 0 else 0.0
        rps_peak = self._calculate_peak_rps(records)
        durations = [r.duration_ms for r in records]
        return TypeMetrics(
            total=len(records),
            rps_mean=rps_mean,
            rps_peak=rps_peak,
            rpm_mean=rps_mean * 60,
            rpm_peak=rps_peak * 60,
            p50_ms=self._percentile(durations, 50),
            p95_ms=self._percentile(durations, 95),
            p99_ms=self._percentile(durations, 99),
            max_concurrent=self._calculate_max_concurrent(records),
        )

    @staticmethod
    def _calculate_peak_rps(records: list[APICallRecord], window_seconds: float = 1.0) -> float:
        """Calculate the peak requests-per-second using a sliding window (two-pointer sweep).

        :param records: Call records to analyze.
        :param window_seconds: Width of the sliding window, in seconds.
        :returns: The maximum number of requests observed in any window of that width.
        """
        if not records:
            return 0.0

        timestamps = sorted(r.timestamp for r in records)
        max_count = 0
        left = 0
        for right, ts in enumerate(timestamps):
            while timestamps[left] <= ts - window_seconds:
                left += 1
            max_count = max(max_count, right - left + 1)

        return max_count / window_seconds

    @staticmethod
    def _percentile(values: list[float], p: int) -> float:
        """Compute the ``p``-th percentile of ``values`` using nearest-rank interpolation.

        :param values: Sample values.
        :param p: Percentile to compute, between 0 and 100.
        :returns: The percentile value, or ``0.0`` if ``values`` is empty.
        """
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((p / 100.0) * len(sorted_values))
        return sorted_values[min(index, len(sorted_values) - 1)]

    @staticmethod
    def _calculate_max_concurrent(records: list[APICallRecord]) -> int:
        """Compute the maximum number of calls that were in flight simultaneously.

        :param records: Call records to analyze.
        :returns: The peak concurrency observed.
        """
        if not records:
            return 0

        events: list[tuple[float, int]] = []
        for record in records:
            start = record.timestamp
            end = record.timestamp + (record.duration_ms / 1000.0)
            events.append((start, 1))
            events.append((end, -1))
        events.sort()

        current = 0
        max_concurrent = 0
        for _, delta in events:
            current += delta
            max_concurrent = max(max_concurrent, current)

        return max_concurrent

    def _get_rate_at_first_429(self) -> dict[str, float]:
        """Compute the per-``api_type`` request rate in the second before the first 429 error.

        :returns: Dict mapping ``api_type`` to requests-per-second, empty if no 429 occurred.
        """
        if not self.errors_429:
            return {}

        first_429 = self.errors_429[0]
        window_start = first_429.timestamp - 1.0

        counts: dict[str, int] = {}
        for r in self.records:
            if window_start <= r.timestamp <= first_429.timestamp:
                counts[r.api_type] = counts.get(r.api_type, 0) + 1

        return {api_type: count / 1.0 for api_type, count in counts.items()}

    def reset(self) -> None:
        """Clear all tracked records (intended for use in tests)."""
        with self._data_lock:
            self.records.clear()
            self.errors_429.clear()
            self.start_time = time.time()


_tracker = APIMetricsTracker()


def get_tracker() -> APIMetricsTracker:
    """Return the process-wide :class:`APIMetricsTracker` singleton."""
    return _tracker
