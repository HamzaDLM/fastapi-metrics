import time
from collections import defaultdict
from typing import DefaultDict

import psutil

from fastapi_metrics_dashboard.backends.base import MetricsStore
from fastapi_metrics_dashboard.logger import logger
from fastapi_metrics_dashboard.backends.base import (
    SystemLogEntry,
    SystemMetricKey,
    Bucket,
)


class InMemoryMetricsStore(MetricsStore):
    def __init__(
        self,
        max_log_samples: int = 10000,
        max_memory_percent: int = 95,
        ttl_seconds: int = 3600,
    ):
        super().__init__()
        self._max_log_samples = max_log_samples
        self._max_memory_percent = max_memory_percent
        self._ttl_seconds = ttl_seconds

        # multi-bucket structure: {bucket_size: {bucket_start_timestamp: {route_path: Bucket}}}
        self._request_buckets = self._make_request_buckets()

        # multi-bucket system metrics: {bucket_size: {bucket_start_timestamp: { metric_name: data }}}
        self._system_buckets = self._make_system_buckets()

    @property
    def _bucket_sizes(self) -> list[int]:
        return [5, 30, 300, 900]  # 5s, 30s, 5min, 15min

    def _get_buckets_for_time_range(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict[int, dict[str, Bucket]]:
        """Get all buckets within a time range for a specific bucket size."""
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

    def _make_request_buckets(
        self,
    ) -> DefaultDict[int, DefaultDict[int, DefaultDict[str, Bucket]]]:
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
    ) -> DefaultDict[
        int, DefaultDict[int, DefaultDict[SystemMetricKey, SystemLogEntry]]
    ]:
        return defaultdict(lambda: defaultdict(lambda: defaultdict()))

    def _get_system_metrics_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict:
        """Get system metrics series for a specific metric and time range."""
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
        self, key: SystemMetricKey, bucket_size: int, data: dict
    ) -> None:
        """Flush system metric data to a specific bucket size."""
        log_entry = SystemLogEntry(**data)
        # logger.debug(
        #     f"STORE: flushing system metrics for bucket size: {bucket_size} metric key: {SystemMetricKey}"
        # )
        async with self._lock:
            self._system_buckets[bucket_size][log_entry["timestamp"]][key] = log_entry

    async def record_request_metrics(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        async with self._lock:
            now = int(time.time())

            for bucket_size in self._bucket_sizes:
                bucket_timestamp = (now // bucket_size) * bucket_size
                route_stats = self._request_buckets[bucket_size][bucket_timestamp][path]

                route_stats["latencies"].append(duration)
                if len(route_stats["latencies"]) > self._max_log_samples:
                    route_stats["latencies"].pop(0)

                route_stats["count"] += 1

                if 400 <= status_code < 600:
                    route_stats["errors"] += 1

                group = f"{status_code // 100}XX"
                route_stats["status_codes"][group] += 1

                route_stats["methods"][method.upper()] += 1

                rw_key = (
                    "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
                )
                route_stats["rw_count"][rw_key] += 1

            # print(json.dumps(dd_to_dict(self._request_buckets), indent=4))

    def _is_memory_safe(self) -> bool:
        avail_memory = psutil.virtual_memory().percent
        logger.debug(f"STORE: check if memory safe, {avail_memory} used")
        return avail_memory < self._max_memory_percent

    def _cleanup_expired_ttl(self) -> None:
        """Clean expired data after TTL"""
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
        """Reset all in-memory metric buckets"""
        self._request_buckets = self._make_request_buckets()
        self._system_buckets = self._make_system_buckets()
        self._system_aggregators = self._make_system_aggregators()
        logger.debug("STORE: store state reset")
