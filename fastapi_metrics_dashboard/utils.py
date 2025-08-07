from collections import deque
from typing import Callable, Deque, Any
import time


def calculate_bucket_size(time_diff_seconds: int, max_points: int = 200) -> int:
    if time_diff_seconds <= 3600:  # 1 hour
        return 10  # 5 second buckets
    elif time_diff_seconds <= 86400:  # 1 day
        return 300  # 5 minute buckets
    elif time_diff_seconds <= 604800:  # 1 week
        return 3600  # 1 hour buckets
    else:
        return max(3600, time_diff_seconds // max_points)


class StatAggregator:
    def __init__(
        self, on_flush: Callable[[dict], None | Any], bucket_size_secs: int = 5
    ) -> None:
        self.bucket_size = bucket_size_secs
        self.samples: Deque[tuple[float, float]] = deque()  # (timestamp, value)
        self.last_flush = time.time()
        self.on_flush = on_flush

    def add_sample(self, value: float) -> None:
        now = time.time()
        self.samples.append((now, value))
        self._check_flush(now)

    def _check_flush(self, now: float) -> None:
        if now - self.last_flush >= self.bucket_size:
            self.flush(now)

    def flush(self, now: float | None = None):
        now = now or time.time()

        values = [v for t, v in self.samples if now - t <= self.bucket_size]
        if not values:
            return

        result = {
            "min": min(values),
            "max": max(values),
            "avg": round((sum(values) / len(values)), 2),
            "timestamp": int(now),
        }

        self.on_flush(result)
        self.samples.clear()
        self.last_flush = now
