import asyncio

import os
from abc import ABC, abstractmethod
from typing import Any, DefaultDict, Literal, TypedDict
import statistics
from collections import defaultdict
from fastapi_metrics_dashboard.logger import logger
from fastapi_metrics_dashboard.utils import StatAggregator

import psutil

proc = psutil.Process(os.getpid())


class SystemLogEntry(TypedDict):
    timestamp: int
    min: float
    max: float
    avg: float


SystemMetricKey = Literal[
    "cpu_percent",
    "memory_percent",
    "memory_used_mb",
    "memory_available_mb",
    "network_io_sent",
    "network_io_recv",
]

StatusCodes = Literal["1XX", "2XX", "3XX", "4XX", "5XX"]
HttpMethods = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTION"]


class Bucket(TypedDict):
    latencies: list[float]
    count: int
    errors: int
    status_codes: DefaultDict[StatusCodes, int]
    methods: DefaultDict[HttpMethods, int]
    rw_count: DefaultDict[Literal["read", "write"], int]


class MetricsStore(ABC):
    def __init__(self):
        self._system_aggregators = self._make_system_aggregators()
        self._lock = asyncio.Lock()

    @property
    @abstractmethod
    def _bucket_sizes(self) -> list[int]:
        pass

    @abstractmethod
    async def record_request_metrics(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        pass

    @abstractmethod
    async def _flush_system_metric_to_bucket(
        self, key: SystemMetricKey, bucket_size: int, data: dict
    ) -> None:
        pass

    @abstractmethod
    def _get_buckets_for_time_range(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict[int, dict[str, Bucket]]:
        pass

    @abstractmethod
    def _get_system_metrics_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict:
        pass

    @abstractmethod
    def _cleanup_expired_ttl(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    def _make_system_aggregators(self) -> dict[int, dict[str, StatAggregator]]:
        return {
            bucket_size: {
                metric: StatAggregator(
                    bucket_size_secs=bucket_size,
                    on_flush=self._create_flush_callback(metric, bucket_size),
                )
                for metric in [
                    "cpu_percent",
                    "memory_percent",
                    "memory_used_mb",
                    "memory_available_mb",
                    "network_io_sent",
                    "network_io_recv",
                ]
            }
            for bucket_size in self._bucket_sizes
        }

    def _create_flush_callback(self, metric_name: SystemMetricKey, bucket_size: int):
        """Create a flush callback for a specific metric and bucket size."""

        def callback(data: dict):
            return asyncio.create_task(
                self._flush_system_metric_to_bucket(metric_name, bucket_size, data)
            )

        return callback

    def _get_bucket_size(
        self, time_range_seconds: int, target_points: int = 150, max_points: int = 250
    ) -> int:
        """Get the optimal bucket size based on time range."""
        ideal_bucket_size = max(
            self._bucket_sizes[0], time_range_seconds // target_points
        )

        suitable_buckets = [bs for bs in self._bucket_sizes if bs >= ideal_bucket_size]

        if suitable_buckets:
            chosen_bucket = min(suitable_buckets)
            actual_points = time_range_seconds // chosen_bucket
            if actual_points <= max_points:
                return chosen_bucket

        for bucket_size in sorted(self._bucket_sizes, reverse=True):
            if time_range_seconds // bucket_size <= max_points:
                return bucket_size

        return max(self._bucket_sizes)

    def _get_status_code_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> list:
        grouped = {
            "1XX": [],
            "2XX": [],
            "3XX": [],
            "4XX": [],
            "5XX": [],
        }

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for ts, routes in buckets.items():
            codes = defaultdict(int)
            for route_data in routes.values():
                for code, count in route_data["status_codes"].items():
                    codes[code] += count
            for code, count in codes.items():
                grouped[code].append([ts, count])

        return [{"name": code, "data": data} for code, data in grouped.items()]

    def _get_read_write_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> list:
        grouped = defaultdict(list)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for ts, routes in buckets.items():
            reads, writes = 0, 0
            for data in routes.values():
                reads += data["rw_count"]["read"]
                writes += data["rw_count"]["write"]
            grouped["Read"].append([ts, reads])
            grouped["Write"].append([ts, writes])

        return [{"name": k, "data": v} for k, v in grouped.items()]

    def _get_latency_series(
        self, bucket_size: int, ts_from: int, ts_to: int, quantile=0.99
    ) -> list:
        route_latency = defaultdict(list)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for ts, routes in buckets.items():
            for route, data in routes.items():
                latencies = data["latencies"]
                if not latencies:
                    continue
                lat = statistics.quantiles(latencies, n=100)[int(quantile * 100) - 1]
                route_latency[route].append([ts, lat])

        return [
            {"name": route, "data": points} for route, points in route_latency.items()
        ]

    def _get_top_routes(
        self, bucket_size: int, ts_from: int, ts_to: int, limit=5
    ) -> dict:
        route_totals = defaultdict(int)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for routes in buckets.values():
            for route, data in routes.items():
                route_totals[route] += data["count"]
        return dict(
            sorted(route_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        )

    def _get_top_slowest_routes(
        self, bucket_size: int, ts_from: int, ts_to: int, count: int = 5
    ) -> dict:
        latency_averages = defaultdict(float)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for bucket in buckets.values():
            for route, data in bucket.items():
                latency_averages[route] = sum(data["latencies"]) / len(
                    data["latencies"]
                )

        return dict(
            sorted(latency_averages.items(), key=lambda item: item[1], reverse=True)[
                :count
            ]
        )

    def _get_top_error_prone_requests(
        self, bucket_size: int, ts_from: int, ts_to: int, count: int = 5
    ) -> dict:
        path_error_count = defaultdict(int)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for bucket in buckets.values():
            for route, data in bucket.items():
                path_error_count[route] += data["errors"]

        return dict(
            sorted(path_error_count.items(), key=lambda item: item[1], reverse=True)[
                :count
            ]
        )

    def get_table_overview(
        self,
        ts_from: int,
        ts_to: int,
    ) -> dict:
        bucket_size = self._get_bucket_size(ts_to - ts_from)
        rows: DefaultDict[str, Any] = defaultdict(
            lambda: {
                "last_called": 0,
                "total_call_count": 0,
                "total_errors_count": 0,
                "requests_per_minute": [],
                "throughput_rps": [],
                "error_rate": 0,
                "p99_latency": [],
            }
        )

        max_values = {
            "p99_latency": 0,
            "error_rate": 0,
        }

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for ts, data in buckets.items():
            for route_path, values in data.items():
                requests_count = sum(values["status_codes"].values())

                rows[route_path]["last_called"] = ts
                rows[route_path]["total_call_count"] += values.get("count", 0)
                rows[route_path]["total_errors_count"] += values["errors"]
                rows[route_path]["requests_per_minute"].append(
                    (60 * requests_count) / bucket_size
                )
                rows[route_path]["throughput_rps"].append(requests_count / bucket_size)
                rows[route_path]["error_rate"] = (
                    rows[route_path]["total_errors_count"] * 100
                ) / rows[route_path]["total_call_count"]
                rows[route_path]["p99_latency"].extend(values["latencies"])

        for _, data in rows.items():
            p99 = statistics.quantiles(data["p99_latency"], n=100)[int(0.99 * 100) - 1]
            if p99 > max_values["p99_latency"]:
                max_values["p99_latency"] = p99
            data["p99_latency"] = p99

            if data["error_rate"] > max_values["error_rate"]:
                max_values["error_rate"] = data["error_rate"]

            data["requests_per_minute"] = round(
                sum(data["requests_per_minute"]) / len(data["requests_per_minute"]), 2
            )

            data["throughput_rps"] = round(
                sum(data["throughput_rps"]) / len(data["throughput_rps"]), 2
            )

        # # # Sort by last_called desc
        # rows.sort(key=itemgetter("last_called"), reverse=True)

        return {
            "rows": rows,
            "max_values": max_values,
            "total": len(rows),
        }

    def _get_requests_per_method(self, bucket_size: int, ts_from: int, ts_to: int):
        methods_count = defaultdict(int)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for values in buckets.values():
            for data in values.values():
                for key, value in data["methods"].items():
                    methods_count[key] += value

        return methods_count

    async def record_system_metrics(self) -> None:
        logger.debug("STORE: recording system metrics")
        memory_info = proc.memory_info()
        memory_used_mb = memory_info.rss / 1024 / 1024
        memory_available_mb = psutil.virtual_memory().available / 1024 / 1024
        memory_percent = (memory_info.rss / psutil.virtual_memory().total) * 100
        net_io = psutil.net_io_counters()
        cpu_percent = round(proc.cpu_percent(interval=None), 3)

        async with self._lock:
            for aggregators in self._system_aggregators.values():
                aggregators["cpu_percent"].add_sample(cpu_percent)
                aggregators["memory_percent"].add_sample(memory_percent)
                aggregators["memory_used_mb"].add_sample(memory_used_mb)
                aggregators["memory_available_mb"].add_sample(memory_available_mb)
                aggregators["network_io_sent"].add_sample(net_io.bytes_sent)
                aggregators["network_io_recv"].add_sample(net_io.bytes_recv)

    def get_metrics(self, ts_from: int, ts_to: int) -> dict[str, Any]:
        bucket_size = self._get_bucket_size(ts_to - ts_from)

        return {
            "latencies": self._get_latency_series(bucket_size, ts_from, ts_to),
            "read_write": self._get_read_write_series(bucket_size, ts_from, ts_to),
            "status_code": self._get_status_code_series(bucket_size, ts_from, ts_to),
            "top_routes": self._get_top_routes(bucket_size, ts_from, ts_to),
            "requests_per_method": self._get_requests_per_method(
                bucket_size, ts_from, ts_to
            ),
            "top_slowest_routes": self._get_top_slowest_routes(
                bucket_size, ts_from, ts_to
            ),
            "top_error_prone_requests": self._get_top_error_prone_requests(
                bucket_size, ts_from, ts_to
            ),
            "system_metrics": self._get_system_metrics_series(
                bucket_size, ts_from, ts_to
            )
            | {
                "num_threads": psutil.cpu_count(logical=True),
            },
            "meta": {
                "bucket_size_secs": bucket_size,
            },
        }
