import time
from collections import defaultdict
from typing import DefaultDict

import psutil

from fastapi_metrics_dashboard.backends import (
    Bucket,
    SystemLogEntry,
)
from fastapi_metrics_dashboard.backends.base import MetricsStore
from fastapi_metrics_dashboard.logger import logger


class InMemoryMetricsStore(MetricsStore):
    """
    In-memory implementation of `MetricsStore` for request and system metrics.

    Metrics are stored in multiple time-bucket resolutions.
    This store is designed for short-lived, high-throughput metrics tracking
    with TTL-based cleanup to prevent unbounded memory growth.

    Attributes:
        _max_memory_percent (int): Memory usage threshold before refusing to store more data.
        _ttl_seconds (int): Time-to-live (in seconds) for stored metrics.
        _request_buckets (DefaultDict): Nested structure holding request-level metrics.
        _system_buckets (DefaultDict): Nested structure holding system-level metrics.
    """

    def __init__(
        self,
        max_memory_percent: int = 95,
        ttl_seconds: int = 3600,
    ):
        super().__init__()
        self._max_memory_percent = max_memory_percent
        self._ttl_seconds = ttl_seconds

        # Multi-bucket structure:
        # {bucket_size: {bucket_start_timestamp: {route_path: Bucket}}}
        self._request_buckets = self._make_request_buckets()

        # Multi-bucket structure for system metrics:
        # {bucket_size: {bucket_start_timestamp: {metric_name: SystemLogEntry}}}
        self._system_buckets = self._make_system_buckets()

    @property
    def bucket_sizes(self) -> list[int]:
        """List of supported bucket sizes (in seconds)."""
        return [5, 30, 300, 900]  # 5s, 30s, 5min, 15min

    def _make_request_buckets(
        self,
    ) -> DefaultDict[int, DefaultDict[int, DefaultDict[str, Bucket]]]:
        """
        Create the nested structure for storing request metrics.

        Returns:
            A defaultdict structure mapping:
                bucket_size -> bucket_timestamp -> route_path -> Bucket
        """
        return defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: Bucket(
                        latencies=[],
                        count=0,
                        errors=0,
                        status_codes=defaultdict(int),
                        methods=defaultdict(int),
                        rw_count=defaultdict(int),
                    )
                )
            )
        )

    def _make_system_buckets(
        self,
    ) -> DefaultDict[int, DefaultDict[int, DefaultDict[str, SystemLogEntry]]]:
        """
        Create the nested structure for storing system metrics.

        Returns:
            A defaultdict structure mapping:
                bucket_size -> bucket_timestamp -> metric_key -> SystemLogEntry
        """
        return defaultdict(lambda: defaultdict(lambda: defaultdict()))

    def get_request_metrics_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict[int, dict[str, dict]]:
        """
        Retrieve request buckets within a specific time range.

        Args:
            bucket_size: Size of buckets (in seconds).
            ts_from: Start timestamp (inclusive).
            ts_to: End timestamp (inclusive).

        Returns:
            Dictionary mapping bucket_start -> {route_path -> Bucket}.
        """
        result = {}

        start_bucket = (ts_from // bucket_size) * bucket_size
        end_bucket = (ts_to // bucket_size) * bucket_size

        current_bucket = start_bucket
        while current_bucket <= end_bucket:
            if current_bucket in self._request_buckets[bucket_size]:
                bucket_end = current_bucket + bucket_size
                if not (bucket_end <= ts_from or current_bucket > ts_to):
                    result[current_bucket] = self._request_buckets[bucket_size][
                        current_bucket
                    ]
            current_bucket += bucket_size

        return result

    def get_system_metrics_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict:
        """
        Retrieve system metrics series for a given time range.

        Args:
            bucket_size: Size of buckets (in seconds).
            ts_from: Start timestamp (inclusive).
            ts_to: End timestamp (inclusive).

        Returns:
            A dictionary mapping SystemMetricKey -> list[SystemLogEntry].
        """
        data_points = defaultdict(list)
        start_bucket = (ts_from // bucket_size) * bucket_size
        end_bucket = (ts_to // bucket_size) * bucket_size

        for bucket_ts in range(start_bucket, end_bucket + bucket_size, bucket_size):
            if bucket_ts not in self._system_buckets[bucket_size].keys():
                continue

            for key, val in self._system_buckets[bucket_size][bucket_ts].items():
                data_points[key].append(val)

        return data_points

    async def _flush_system_metric_to_bucket(
        self, key: str, bucket_size: int, data: dict
    ) -> None:
        """
        Flush system metric data into a specific bucket.

        Args:
            key: System metric identifier.
            bucket_size: Size of bucket (in seconds).
            data: Raw system metric data.
        """
        log_entry = SystemLogEntry(**data)

        async with self._lock:
            self._system_buckets[bucket_size][log_entry["timestamp"]][key] = log_entry

    def record_request_metrics(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        """
        Record request-level metrics into all bucket resolutions.

        Args:
            path: The request path (route).
            duration: Request latency in seconds.
            status_code: HTTP status code of the response.
            method: HTTP method of the request (GET, POST, etc.).
        """
        now = int(time.time())

        for bucket_size in self.bucket_sizes:
            bucket_timestamp = (now // bucket_size) * bucket_size
            route_stats = self._request_buckets[bucket_size][bucket_timestamp][path]

            route_stats["latencies"].append(duration)

            route_stats["count"] += 1

            if 400 <= status_code < 600:
                route_stats["errors"] += 1

            group = f"{status_code // 100}XX"
            route_stats["status_codes"][group] += 1

            route_stats["methods"][method.upper()] += 1

            rw_key = "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
            route_stats["rw_count"][rw_key] += 1

    def _is_memory_safe(self) -> bool:
        """
        Check if current memory usage is below the safety threshold.

        Returns:
            True if memory usage < `_max_memory_percent`.
        """
        avail_memory = psutil.virtual_memory().percent
        logger.debug(f"STORE: check if memory safe, {avail_memory} used")
        return avail_memory < self._max_memory_percent

    def _cleanup_expired_ttl(self) -> None:
        """
        Removes old request and system buckets whose age exceeds `_ttl_seconds`.
        """
        logger.debug("STORE: cleaning up expired data...")
        now = time.time()

        for bucket_size in list(self._request_buckets.keys()):
            for bucket_start in list(self._request_buckets[bucket_size].keys()):
                if now - bucket_start > self._ttl_seconds:
                    del self._request_buckets[bucket_size][bucket_start]

        for bucket_size in list(self._system_buckets.keys()):
            for bucket_start in list(self._system_buckets[bucket_size].keys()):
                if now - bucket_start > self._ttl_seconds:
                    del self._request_buckets[bucket_size][bucket_start]

    def reset(self) -> None:
        """
        Reset all metrics.

        Clears request buckets, system buckets, and re-initializes
        system aggregators to their default state.
        """
        self._request_buckets = self._make_request_buckets()
        self._system_buckets = self._make_system_buckets()
        self._system_aggregators = self._make_system_aggregators()
        logger.debug("STORE: store state reset")
