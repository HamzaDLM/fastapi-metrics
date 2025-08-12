import asyncio
import os
import statistics
import time
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Literal, TypedDict

import psutil

from fastapi_metrics_dashboard.backends.base import MetricsStore
from fastapi_metrics_dashboard.utils import StatAggregator

proc = psutil.Process(os.getpid())


class RequestLogEntry(TypedDict):
    timestamp: int
    path: str
    status_code: int
    latency: float
    method: str


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


class InMemoryMetricsStore(MetricsStore):
    def __init__(
        self,
        max_log_samples: int = 10000,
        max_memory_percent: int = 95,
    ):
        self._max_log_samples = max_log_samples
        self._max_memory_percent = max_memory_percent

        self._bucket_sizes = [5, 30, 300, 900]  # 5s, 30s, 5min, 15min

        # multi-bucket structure: {bucket_size: {bucket_start_timestamp: {route_path: Bucket}}}
        self._request_buckets: DefaultDict[
            int, DefaultDict[int, DefaultDict[str, Bucket]]
        ] = defaultdict(
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

        # multi-bucket system metrics: {bucket_size: {bucket_start_timestamp: { metric_name: data }}}
        self._system_buckets: DefaultDict[
            int,
            DefaultDict[int, DefaultDict[SystemMetricKey, SystemLogEntry]],
        ] = defaultdict(lambda: defaultdict(lambda: defaultdict()))

        self._system_aggregators = {}
        for bucket_size in self._bucket_sizes:
            self._system_aggregators[bucket_size] = {
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

        self._lock = asyncio.Lock()

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

    def _create_flush_callback(self, metric_name: SystemMetricKey, bucket_size: int):
        """Create a flush callback for a specific metric and bucket size."""

        def callback(data: dict):
            return asyncio.create_task(
                self._flush_system_metric_to_bucket(metric_name, bucket_size, data)
            )

        return callback

    async def record_system_metrics(self) -> None:
        memory_info = proc.memory_info()
        memory_used_mb = memory_info.rss / 1024 / 1024
        memory_available_mb = psutil.virtual_memory().available / 1024 / 1024
        memory_percent = (memory_info.rss / psutil.virtual_memory().total) * 100
        net_io = psutil.net_io_counters()
        cpu_percent = round(proc.cpu_percent(interval=None), 2)

        async with self._lock:
            for aggregators in self._system_aggregators.values():
                aggregators["cpu_percent"].add_sample(cpu_percent)
                aggregators["memory_percent"].add_sample(memory_percent)
                aggregators["memory_used_mb"].add_sample(memory_used_mb)
                aggregators["memory_available_mb"].add_sample(memory_available_mb)
                aggregators["network_io_sent"].add_sample(net_io.bytes_sent)
                aggregators["network_io_recv"].add_sample(net_io.bytes_recv)

    async def _flush_system_metric_to_bucket(
        self, key: SystemMetricKey, bucket_size: int, data: dict
    ) -> None:
        """Flush system metric data to a specific bucket size."""
        log_entry = SystemLogEntry(**data)

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

    def _get_buckets_for_time_range(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> Dict[int, Dict[str, Bucket]]:
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

    def _get_table_overview(
        self,
        bucket_size: int,
        ts_from: int,
        ts_to: int,
        page: int = 1,
        limit: int = 10,
        search_term: str | None = None,
    ) -> dict:
        rows: DefaultDict[str, Any] = defaultdict(
            lambda: {
                "last_called": 0,
                "total_call_count": 0,
                "total_errors_count": 0,
                "requests_per_min": [],
                "error_rate": [],
                "p99_latency": [],
            }
        )

        # "latencies": [],
        # "count": 0,
        # "errors": 0,
        # "status_codes": defaultdict(int),
        # "methods": defaultdict(int),
        # "rw_count": defaultdict(int),

        max_latency = 0
        max_error_rate = 0
        max_requests_min = 0

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for ts, data in buckets.items():
            for route_path, values in data.items():

                rows[route_path]["last_called"] = ts  # compare with latest
                rows[route_path]["total_call_count"] += values.get("count", 0)
                rows[route_path]["total_errors_count"] += values["errors"]
                # rows[route_path]["requests_per_min"] =
                rows[route_path]["error_rate"] = (
                    rows[route_path]["total_errors_count"] * 100
                ) / rows[route_path]["total_call_count"]
                rows[route_path]["p99_latency"].extend(values["latencies"])

        for _, data in rows.items():
            data["p99_latency"] = statistics.quantiles(data["p99_latency"], n=100)[
                int(0.99 * 100) - 1
            ]

        # # Sort by last_called desc
        # items.sort(key=itemgetter("last_called"), reverse=True)

        # # Max values (used for bar comparisons in UI)
        # max_requests_per_min = max((i["requests_per_min"] for i in items), default=1)
        # max_error_rate = max((i["error_rate"] for i in items), default=1)
        # max_p99_latency = max((i["p99_latency"] for i in items), default=1)

        # Apply pagination
        # start = (page - 1) * limit
        # end = start + limit
        # paginated = rows[start:end]

        # # Inject max values into each row
        # for item in paginated:
        #     item["max_requests_per_min"] = max_requests_per_min
        #     item["max_error_rate"] = max_error_rate
        #     item["max_p99_latency"] = max_p99_latency

        return {
            "rows": rows,
            "total": len(rows),
            "page": page,
            "page_size": limit,
        }

    def _get_requests_per_method(self, bucket_size: int, ts_from: int, ts_to: int):
        methods_count = defaultdict(int)

        buckets = self._get_buckets_for_time_range(bucket_size, ts_from, ts_to)
        for values in buckets.values():
            for data in values.values():
                for key, value in data["methods"].items():
                    methods_count[key] += value

        return methods_count

    def _get_bucket_size(
        self, time_range_seconds: int, target_points: int = 150, max_points: int = 250
    ) -> int:
        """Get the optimal bucket size based on time range."""
        ideal_bucket_size = max(
            self._bucket_sizes[0], time_range_seconds // target_points
        )

        # find the closest bucket size >= ideal
        suitable_buckets = [bs for bs in self._bucket_sizes if bs >= ideal_bucket_size]

        if suitable_buckets:
            chosen_bucket = min(suitable_buckets)
            # verify it doesn't exceed max_points
            actual_points = time_range_seconds // chosen_bucket
            if actual_points <= max_points:
                return chosen_bucket

        # fallback: find bucket that gives closest to target_points without exceeding max_points
        for bucket_size in sorted(self._bucket_sizes, reverse=True):
            if time_range_seconds // bucket_size <= max_points:
                return bucket_size

        # largest bucket as final resort
        return max(self._bucket_sizes)

    async def get_metrics(self, ts_from: int, ts_to: int) -> Dict[str, Any]:
        bucket_size = self._get_bucket_size(ts_to - ts_from)

        # print(
        #     f"ts from: {ts_from}, ts to: {ts_to} diff: {ts_to - ts_from} bucket size: {bucket_size}"
        # )

        async with self._lock:
            return {
                "latencies": self._get_latency_series(bucket_size, ts_from, ts_to),
                "read_write": self._get_read_write_series(bucket_size, ts_from, ts_to),
                "status_code": self._get_status_code_series(
                    bucket_size, ts_from, ts_to
                ),
                "top_routes": self._get_top_routes(bucket_size, ts_from, ts_to),
                "overview_table": self._get_table_overview(bucket_size, ts_from, ts_to),
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

    def _is_memory_safe(self) -> bool:
        return psutil.virtual_memory().percent < self._max_memory_percent

    def _clean():
        pass

    def reset():
        pass
