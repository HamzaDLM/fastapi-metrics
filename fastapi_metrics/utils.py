import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Deque


class StatAggregator:
    """
    Aggregate numeric samples into fixed-size time buckets and compute statistics.

    This class collects streaming numeric values (samples) and periodically
    flushes aggregated statistics (min, max, average) for each completed
    time bucket. A callback (`on_flush`) is invoked whenever a bucket
    is ready to be flushed.

    Attributes:
        bucket_size (int): The size of each aggregation bucket in seconds.
        samples (Deque[tuple[float, float]]): A queue of (timestamp, value) samples.
        on_flush (Callable[[dict], None | Any]): Callback invoked when a bucket is flushed.
        last_flush (float): The timestamp of the last flush, aligned to the bucket size.
    """

    def __init__(
        self, on_flush: Callable[[dict], None | Any], bucket_size_secs: int = 5
    ) -> None:
        """
        Initialize a StatAggregator.

        Args:
            on_flush: A callback function that receives a dictionary containing
                aggregated statistics when a bucket is flushed. Example result:
                {
                    "min": float,
                    "max": float,
                    "avg": float,
                    "timestamp": int  # aligned bucket timestamp
                }

            bucket_size_secs: The duration (in seconds) of each aggregation bucket.
        """
        self.bucket_size = bucket_size_secs
        self.samples: Deque[tuple[float, float]] = deque()
        self.on_flush = on_flush

        now = time.time()
        self.last_flush = self._get_aligned_timestamp(now)

    def _get_aligned_timestamp(self, timestamp: float) -> float:
        """
        Align a timestamp down to the nearest bucket boundary.

        Example:
            If bucket_size = 5 and timestamp = 1754763422,
            returns 1754763420.

        Args:
            timestamp: Unix timestamp in seconds.

        Returns:
            The aligned timestamp (float).
        """
        return (int(timestamp) // self.bucket_size) * self.bucket_size

    def _get_next_flush_time(self, current_time: float) -> float:
        """
        Compute the timestamp of the next flush boundary.

        Args:
            current_time: Current Unix timestamp.

        Returns:
            Next aligned flush time.
        """
        current_aligned = self._get_aligned_timestamp(current_time)
        return current_aligned + self.bucket_size

    def add_sample(self, value: float) -> None:
        """
        Add a numeric sample to the aggregator.

        This may trigger a flush if the current bucket window has passed.

        Args:
            value: The numeric sample value to record.
        """
        now = time.time()
        self.samples.append((now, value))

        next_flush_time = self._get_next_flush_time(self.last_flush)

        if now >= next_flush_time:
            self.flush(next_flush_time)

    def flush(self, flush_timestamp: float | None = None):
        """
        Flush the current bucket and compute statistics.

        Collects all samples within the last bucket window,
        computes min/max/average, and calls the `on_flush` callback.

        Args:
            flush_timestamp: Optional explicit flush time. If None,
                the current time is used.

        Notes:
            - Samples older than 2x bucket_size are discarded.
            - If no samples exist in the window, the flush is skipped.
        """
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

        cutoff_time = flush_timestamp - (self.bucket_size * 2)
        while self.samples and self.samples[0][0] < cutoff_time:
            self.samples.popleft()

        self.last_flush = flush_timestamp


def defaultdict_to_dict(d: Any) -> Any:
    """Recursively convert defaultdict to dict."""
    if isinstance(d, defaultdict):
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    elif isinstance(d, dict):
        d = {k: defaultdict_to_dict(v) for k, v in d.items()}
    return d


def timestamp_to_readable(ts: Any) -> str:
    """Convert timestamp to readable form time."""
    if ts and type(ts) is int:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return str(ts)
