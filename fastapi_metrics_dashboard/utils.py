from collections import deque, defaultdict
from typing import Callable, Deque, Any
import time


class StatAggregator:
    def __init__(
        self, on_flush: Callable[[dict], None | Any], bucket_size_secs: int = 5
    ) -> None:
        self.bucket_size = bucket_size_secs
        self.samples: Deque[tuple[float, float]] = deque()  # (timestamp, value)
        self.on_flush = on_flush

        now = time.time()
        self.last_flush = self._get_aligned_timestamp(now)

    def _get_aligned_timestamp(self, timestamp: float) -> float:
        """Get the aligned timestamp based on bucket size. e.g. 1754763422 => 1754763420"""
        return (int(timestamp) // self.bucket_size) * self.bucket_size

    def _get_next_flush_time(self, current_time: float) -> float:
        """Get the next aligned flush time."""
        current_aligned = self._get_aligned_timestamp(current_time)
        return current_aligned + self.bucket_size

    def add_sample(self, value: float) -> None:
        now = time.time()
        self.samples.append((now, value))
        self._check_flush(now)

    def _check_flush(self, now: float) -> None:
        next_flush_time = self._get_next_flush_time(self.last_flush)

        if now >= next_flush_time:
            self.flush(next_flush_time)

    def flush(self, flush_timestamp: float | None = None):
        if flush_timestamp is None:
            flush_timestamp = time.time()

        bucket_start = flush_timestamp - self.bucket_size
        values = [v for t, v in self.samples if bucket_start <= t < flush_timestamp]

        if not values:
            self.last_flush = flush_timestamp
            return

        result = {
            "min": min(values),
            "max": max(values),
            "avg": round((sum(values) / len(values)), 2),
            "timestamp": int(flush_timestamp),
        }

        self.on_flush(result)

        # Remove old samples that are outside any reasonable window
        cutoff_time = flush_timestamp - (self.bucket_size * 2)
        while self.samples and self.samples[0][0] < cutoff_time:
            self.samples.popleft()

        self.last_flush = flush_timestamp


def dd_to_dict(d: Any) -> Any:
    """Recursively convert defaultdict to dict."""
    if isinstance(d, defaultdict):
        d = {k: dd_to_dict(v) for k, v in d.items()}
    elif isinstance(d, dict):
        d = {k: dd_to_dict(v) for k, v in d.items()}
    return d
