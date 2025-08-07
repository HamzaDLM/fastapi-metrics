import asyncio
import os
import pprint
import statistics
import time
from collections import defaultdict, deque
from typing import Any, DefaultDict, Deque, Dict, Literal, TypedDict

import psutil

from fastapi_metrics_dashboard.backends.base import MetricsStore
from fastapi_metrics_dashboard.utils import StatAggregator, calculate_bucket_size

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


class SystemMetrics(TypedDict):
    cpu_percent: Deque[SystemLogEntry]
    memory_percent: Deque[SystemLogEntry]
    memory_used_mb: Deque[SystemLogEntry]
    memory_available_mb: Deque[SystemLogEntry]
    network_io_sent: Deque[SystemLogEntry]
    network_io_recv: Deque[SystemLogEntry]


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
        bucket_size_secs: int = 10,
        max_memory_percent: int = 95,
    ):
        self._max_log_samples = max_log_samples
        self._bucket_size_secs = bucket_size_secs
        self._max_memory_percent = max_memory_percent

        """
            {
                bucket_size: {
                    system_logs: {

                    },
                    request_logs: {
                    
                    }
                }
            }
        """

        # timestamp => route_path => { latenc... }
        self._buckets: DefaultDict[int, DefaultDict[str, Bucket]] = defaultdict(
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

        self._system_metrics: SystemMetrics = SystemMetrics(
            cpu_percent=deque(maxlen=max_log_samples),
            memory_percent=deque(maxlen=max_log_samples),
            memory_used_mb=deque(maxlen=max_log_samples),
            memory_available_mb=deque(maxlen=max_log_samples),
            network_io_sent=deque(maxlen=max_log_samples),
            network_io_recv=deque(maxlen=max_log_samples),
        )

        self._cpu_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("cpu_percent", data)
            ),
        )
        self._memory_percent_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("memory_percent", data),
            ),
        )
        self._memory_used_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("memory_used_mb", data)
            ),
        )
        self._memory_available_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("memory_available_mb", data),
            ),
        )
        self._net_io_sent_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("network_io_sent", data),
            ),
        )
        self._net_io_recv_aggregator = StatAggregator(
            bucket_size_secs=bucket_size_secs,
            on_flush=lambda data: asyncio.create_task(
                self._flush_system_metric("network_io_recv", data),
            ),
        )

        self._lock = asyncio.Lock()

    async def record_request_log(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        async with self._lock:
            now = int(time.time())
            bucket = now - (now % self._bucket_size_secs)
            route_stats = self._buckets[bucket][path]

            route_stats["latencies"].append(duration)
            if len(route_stats["latencies"]) > self._max_log_samples:
                route_stats["latencies"].pop(0)

            route_stats["count"] += 1

            if 400 <= status_code < 600:
                route_stats["errors"] += 1

            group = f"{status_code // 100}XX"
            route_stats["status_codes"][group] += 1

            route_stats["methods"][method.upper()] += 1

            rw_key = "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
            route_stats["rw_count"][rw_key] += 1

    def _get_status_code_series(self) -> list:
        grouped = {
            "1XX": [],
            "2XX": [],
            "3XX": [],
            "4XX": [],
            "5XX": [],
        }

        for ts, routes in self._buckets.items():
            codes = defaultdict(int)
            for route_data in routes.values():
                for code, count in route_data["status_codes"].items():
                    codes[code] += count
            for code, count in codes.items():
                grouped[code].append([ts, count])

        return [{"name": code, "data": data} for code, data in grouped.items()]

    def _get_read_write_series(self) -> list:
        grouped = defaultdict(list)

        for ts, routes in self._buckets.items():
            reads, writes = 0, 0
            for data in routes.values():
                reads += data["rw_count"]["read"]
                writes += data["rw_count"]["write"]
            grouped["Read"].append([ts, reads])
            grouped["Write"].append([ts, writes])

        return [{"name": k, "data": v} for k, v in grouped.items()]

    def _get_latency_series(self, quantile=0.99) -> list:
        route_latency = defaultdict(list)

        for ts, routes in self._buckets.items():
            for route, data in routes.items():
                latencies = data["latencies"]
                if not latencies:
                    continue
                lat = statistics.quantiles(latencies, n=100)[int(quantile * 100) - 1]
                route_latency[route].append([ts, lat])

        return [
            {"name": route, "data": points} for route, points in route_latency.items()
        ]

    def _get_top_routes(self, limit=5) -> dict:
        route_totals = defaultdict(int)

        for routes in self._buckets.values():
            for route, data in routes.items():
                route_totals[route] += data["count"]
        return dict(
            sorted(route_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        )

    def _get_top_slowest_routes(self, count: int = 5) -> dict:
        latency_averages = defaultdict(float)

        for bucket in self._buckets.values():
            for route, data in bucket.items():
                latency_averages[route] = sum(data["latencies"]) / len(
                    data["latencies"]
                )

        return dict(
            sorted(latency_averages.items(), key=lambda item: item[1], reverse=True)[
                :count
            ]
        )

    def _get_top_error_prone_requests(self, count: int = 5) -> dict:
        path_error_count = defaultdict(int)

        for bucket in self._buckets.values():
            for route, data in bucket.items():
                path_error_count[route] += data["errors"]

        return dict(
            sorted(path_error_count.items(), key=lambda item: item[1], reverse=True)[
                :count
            ]
        )

    def _get_table_overview(
        self, page: int = 1, limit: int = 10, search_term: str | None = None
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

        for ts, data in self._buckets.items():
            for route_path, values in data.items():
                # print(route_path, rows[route_path], values.get("count", 0))

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

    def _get_requests_per_method(self):
        methods_count = defaultdict(int)
        for _, values in self._buckets.items():
            for _, data in values.items():
                for key, value in data["methods"].items():
                    methods_count[key] += value

        return methods_count

    def _print_buckets(self):
        clean = {}
        for bucket_ts, routes in self._buckets.items():
            clean[bucket_ts] = {}
            for route, data in routes.items():
                clean[bucket_ts][route] = {
                    "count": data["count"],
                    "errors": data["errors"],
                    "latencies": list(data["latencies"]),
                    "status_codes": dict(data["status_codes"]),
                    "methods": dict(data["methods"]),
                    "rw_count": dict(data["rw_count"]),
                }
        pprint.pprint(clean, sort_dicts=False)

    async def _flush_system_metric(self, key: SystemMetricKey, data: dict) -> None:
        log_entry = SystemLogEntry(**data)
        async with self._lock:
            self._system_metrics[key].append(log_entry)

    async def record_system_metrics(self) -> None:
        memory_info = proc.memory_info()
        memory_used_mb = memory_info.rss / 1024 / 1024
        memory_available_mb = psutil.virtual_memory().available / 1024 / 1024
        memory_percent = (memory_info.rss / psutil.virtual_memory().total) * 100
        net_io = psutil.net_io_counters()

        async with self._lock:
            self._cpu_aggregator.add_sample(round(proc.cpu_percent(interval=None), 2))
            print(self._system_metrics["cpu_percent"])
            self._memory_percent_aggregator.add_sample(memory_percent)
            self._memory_used_aggregator.add_sample(memory_used_mb)
            self._memory_available_aggregator.add_sample(memory_available_mb)
            self._net_io_sent_aggregator.add_sample(net_io.bytes_sent)
            self._net_io_recv_aggregator.add_sample(net_io.bytes_recv)

    async def get_apexchart_timeseries_format(self):
        pass

    async def get_metrics(self, ts_from: int, ts_to: int) -> Dict[str, Any]:
        bucket_duration = calculate_bucket_size(ts_to - ts_from)

        system_metrics = {
            key: self._reaggregate_sys_metrics(
                list(entries), ts_from, ts_to, bucket_duration
            )
            for key, entries in self._system_metrics.items()
        }

        async with self._lock:
            return {
                "latencies": self._get_latency_series(),
                "read_write": self._get_read_write_series(),
                "status_code": self._get_status_code_series(),
                "top_routes": self._get_top_routes(),
                "overview_table": self._get_table_overview(),
                "requests_per_method": self._get_requests_per_method(),
                "top_slowest_routes": self._get_top_slowest_routes(),
                "top_error_prone_requests": self._get_top_error_prone_requests(),
                "system": system_metrics
                | {
                    "num_threads": psutil.cpu_count(logical=True),
                    "bucket_size_secs": bucket_duration,
                },
            }

    def _reaggregate(
        self,
        entries: list[dict[str, Any]],
        ts_from: int,
        ts_to: int,
        new_bucket_size: int,
    ) -> list[dict[str, Any]]:
        """
        Reaggregates metric entries into new time buckets.

        Args:
            entries: List of dicts with keys 'value', and 'timestamp'.
            ts_from: Start of time window (inclusive).
            ts_to: End of time window (inclusive).
            new_bucket_size: Size of each time bucket in seconds.

        Returns:
            A list of reaggregated metric dicts, each with 'value' and 'timestamp'.
        """
        buckets = defaultdict(list)

        for entry in entries:
            ts = entry["timestamp"]
            if ts_from <= ts <= ts_to:
                new_bucket = (ts // new_bucket_size) * new_bucket_size
                buckets[new_bucket].append({**entry})

        return [
            {"timestamp": ts, "value": sum(vals) / len(vals)}
            for ts, vals in sorted(buckets.items())
        ]

    def _reaggregate_sys_metrics(
        self,
        entries: list[dict[str, Any]],
        ts_from: int,
        ts_to: int,
        new_bucket_size: int,
    ) -> list[dict[str, Any]]:
        """
        Reaggregates system metric entries into new time buckets.

        Args:
            entries: List of dicts with keys 'min', 'max', 'avg', and 'timestamp'.
            ts_from: Start of time window (inclusive).
            ts_to: End of time window (inclusive).
            new_bucket_size: Size of each time bucket in seconds.

        Returns:
            A list of reaggregated metric dicts, each with 'min', 'max', 'avg', and 'timestamp'.
        """
        buckets = defaultdict(list)

        for entry in entries:
            ts = entry["timestamp"]
            if ts_from <= ts <= ts_to:
                new_bucket = (ts // new_bucket_size) * new_bucket_size
                buckets[new_bucket].append({**entry})

        result = []
        for ts, bucket_entries in sorted(buckets.items()):
            if not bucket_entries:
                continue

            mins = [val["min"] for val in bucket_entries]
            maxs = [val["max"] for val in bucket_entries]
            avgs = [val["avg"] for val in bucket_entries]

            result.append(
                {
                    "min": min(mins),
                    "max": max(maxs),
                    "avg": sum(avgs) / len(avgs),
                    "timestamp": ts,
                }
            )

        return result

    def _is_memory_safe(self) -> bool:
        return psutil.virtual_memory().percent < self._max_memory_percent
