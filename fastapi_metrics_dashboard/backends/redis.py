import json
import time
from collections import defaultdict

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from fastapi_metrics_dashboard.backends import Bucket
from fastapi_metrics_dashboard.backends.base import AsyncMetricsStore, MetricsStore


class RedisMetricsStore(MetricsStore):
    """
    Redis implementation of `MetricsStore` for request and system metrics.

    Metrics are stored in multiple time-bucket resolutions
    with optional TTL-based cleanup.

    Attributes:
        client (redis.client.Redis): Synchronous redis client.
        _ttl_seconds (int): Time-to-live (in seconds) for stored metrics.
    """

    def __init__(self, client: SyncRedis, ttl_seconds: int | None = None):
        super().__init__()
        if client is not None and not isinstance(client, SyncRedis):
            raise TypeError(f"Expected redis.client.Redis client, got {type(client).__name__}")
        self.ttl_seconds = ttl_seconds
        self.client = client

    def check_health(self):
        return self.client.ping()

    @property
    def bucket_sizes(self) -> list[int]:
        """List of supported bucket sizes (in seconds)."""
        return [5, 30, 300, 900]  # 5s, 30s, 5min, 15min

    async def _flush_system_metric_to_bucket(self, key: str, bucket_size: int, data: dict) -> None:
        """
        Flush system metric data into a specific bucket.

        Args:
            key: System metric identifier.
            bucket_size: Size of bucket (in seconds).
            data: Raw system metric data.
        """
        base_key = f"system-metrics:{bucket_size}:{data['timestamp']}"

        self.client.hset(
            base_key,
            key,
            json.dumps(data),
        )

        if self.ttl_seconds:
            self.client.expire(base_key, self.ttl_seconds)

    def record_request_metrics(self, path: str, duration: float, status_code: int, method: str) -> None:
        """
        Record request-level metrics into all bucket resolutions.

        Format:
            request-metrics:{bucket_size}:{bucket_ts} = {
                {request_route} = {
                    {metric_name} = data
                }
                ...
            }

        Args:
            path: The request path (route).
            duration: Request latency in seconds.
            status_code: HTTP status code of the response.
            method: HTTP method of the request (GET, POST, etc.).
        """
        now = int(time.time())

        for bucket_size in self.bucket_sizes:
            bucket_timestamp = (now // bucket_size) * bucket_size
            base_key = f"request-metrics:{bucket_size}:{bucket_timestamp}"

            route_stats = Bucket(
                latencies=[],
                count=0,
                errors=0,
                status_codes=defaultdict(int),
                methods=defaultdict(int),
                rw_count=defaultdict(int),
            )

            if self.client.exists(base_key):
                if self.client.hexists(base_key, path):
                    existing_metrics = self.client.hget(base_key, path)
                    route_stats = json.loads(existing_metrics.decode("utf-8"))  # type: ignore[union-attr]

            route_stats["latencies"].append(duration)
            route_stats["count"] += 1

            if 400 <= status_code < 600:
                route_stats["errors"] += 1

            group = f"{status_code // 100}XX"
            if group in route_stats["status_codes"]:
                route_stats["status_codes"][group] += 1
            else:
                route_stats["status_codes"][group] = 1

            route_stats["methods"][method.upper()] += 1

            if "read" not in route_stats["rw_count"]:
                route_stats["rw_count"]["read"] = 0
            if "write" not in route_stats["rw_count"]:
                route_stats["rw_count"]["write"] = 0

            rw_key = "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
            route_stats["rw_count"][rw_key] += 1

            self.client.hset(base_key, f"{path}", json.dumps(route_stats))

            if self.ttl_seconds:
                self.client.expire(base_key, self.ttl_seconds)

    def get_request_metrics_series(self, bucket_size: int, ts_from: int, ts_to: int) -> dict[int, dict[str, dict]]:
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
            base_key = f"request-metrics:{bucket_size}:{current_bucket}"

            bucket_exists = self.client.exists(base_key)

            if bucket_exists:
                bucket_end = current_bucket + bucket_size
                if not (bucket_end <= ts_from or current_bucket > ts_to):
                    bucket_data = self.client.hgetall(base_key)
                    result[current_bucket] = {
                        route.decode(): json.loads(bucket.decode("utf-8"))
                        for route, bucket in bucket_data.items()  # type: ignore[union-attr]
                    }

            current_bucket += bucket_size

        return result

    def get_system_metrics_series(self, bucket_size: int, ts_from: int, ts_to: int) -> dict:
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
            redis_key = f"system-metrics:{bucket_size}:{bucket_ts}"

            bucket_data = self.client.hgetall(redis_key)
            if not bucket_data:
                continue

            for key, val in bucket_data.items():  # type: ignore[union-attr]
                data_points[key.decode()].append(json.loads(val.decode()))

        return data_points

    def _cleanup_expired_ttl(self) -> None:
        """Redis automatically handles TTL expiration; nothing to clean up here."""
        return None

    def reset(self) -> None:
        """
        Reset all metrics.

        Clears request buckets, system buckets, and re-initializes
        system aggregators to their default state.
        """
        for pattern in ["system-metrics:*", "request-metrics:*"]:
            cursor = 0
            while True:
                cursor, keys = self.client.scan(cursor=cursor, match=pattern, count=100)  # type: ignore
                if keys:
                    self.client.delete(*keys)
                if cursor == 0:
                    break

        self._system_aggregators = self._make_system_aggregators()


class AsyncRedisMetricsStore(AsyncMetricsStore):
    """
    Async Redis implementation of `MetricsStore` for request and system metrics.

    Metrics are stored in multiple time-bucket resolutions
    with optional TTL-based cleanup.

    Attributes:
        client (redis.asyncio.client.Redis): Asynchronous redis client.
        _ttl_seconds (int): Time-to-live (in seconds) for stored metrics.
    """

    def __init__(self, client: AsyncRedis, ttl_seconds: int | None = None):
        super().__init__()
        if client is not None and not isinstance(client, AsyncRedis):
            raise TypeError(f"Expected redis.asyncio.client.Redis client, got {type(client).__name__}")
        self.ttl_seconds = ttl_seconds
        self.client = client

        # print("ping:", self.check_health())

    async def check_health(self):
        return await self.client.ping()

    @property
    def bucket_sizes(self) -> list[int]:
        return [5, 30, 300, 900]  # 5s, 30s, 5min, 15min

    async def _flush_system_metric_to_bucket(self, key: str, bucket_size: int, data: dict) -> None:
        """
        Flush system metric data into a specific bucket.

        Args:
            key: System metric identifier.
            bucket_size: Size of bucket (in seconds).
            data: Raw system metric data.
        """
        base_key = f"system-metrics:{bucket_size}:{data['timestamp']}"

        await self.client.hset(
            base_key,
            key,
            json.dumps(data),
        )  # type: ignore

        if self.ttl_seconds:
            self.client.expire(base_key, self.ttl_seconds)

    async def record_request_metrics(self, path: str, duration: float, status_code: int, method: str) -> None:
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
            base_key = f"request-metrics:{bucket_size}:{bucket_timestamp}"

            route_stats = Bucket(
                latencies=[],
                count=0,
                errors=0,
                status_codes=defaultdict(int),
                methods=defaultdict(int),
                rw_count=defaultdict(int),
            )

            if await self.client.exists(base_key):
                if await self.client.hexists(base_key, path):  # type: ignore
                    existing_metrics = await self.client.hget(base_key, path)  # type: ignore
                    route_stats = json.loads(existing_metrics.decode("utf-8"))  # type: ignore[union-attr]

            route_stats["latencies"].append(duration)
            route_stats["count"] += 1

            if 400 <= status_code < 600:
                route_stats["errors"] += 1

            group = f"{status_code // 100}XX"
            if group in route_stats["status_codes"]:
                route_stats["status_codes"][group] += 1
            else:
                route_stats["status_codes"][group] = 1

            route_stats["methods"][method.upper()] += 1

            if "read" not in route_stats["rw_count"]:
                route_stats["rw_count"]["read"] = 0
            if "write" not in route_stats["rw_count"]:
                route_stats["rw_count"]["write"] = 0

            rw_key = "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
            route_stats["rw_count"][rw_key] += 1

            await self.client.hset(base_key, f"{path}", json.dumps(route_stats))  # type: ignore

            if self.ttl_seconds:
                await self.client.expire(base_key, self.ttl_seconds)

    async def get_request_metrics_series(
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
            base_key = f"request-metrics:{bucket_size}:{current_bucket}"

            bucket_exists = await self.client.exists(base_key)

            if bucket_exists:
                bucket_end = current_bucket + bucket_size
                if not (bucket_end <= ts_from or current_bucket > ts_to):
                    bucket_data = await self.client.hgetall(base_key)  # type: ignore
                    result[current_bucket] = {
                        route.decode(): json.loads(bucket.decode("utf-8"))
                        for route, bucket in bucket_data.items()  # type: ignore[union-attr]
                    }

            current_bucket += bucket_size

        return result

    async def get_system_metrics_series(self, bucket_size: int, ts_from: int, ts_to: int) -> dict:
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
            redis_key = f"system-metrics:{bucket_size}:{bucket_ts}"

            bucket_data = await self.client.hgetall(redis_key)  # type: ignore
            if not bucket_data:
                continue

            for key, val in bucket_data.items():  # type: ignore[union-attr]
                data_points[key.decode()].append(json.loads(val.decode()))

        return data_points

    async def _cleanup_expired_ttl(self) -> None: ...

    async def reset(self) -> None:
        """
        Reset all metrics.

        Clears request buckets, system buckets, and re-initializes
        system aggregators to their default state.
        """
        for pattern in ["system-metrics:*", "request-metrics:*"]:
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor=cursor, match=pattern, count=100)  # type: ignore
                if keys:
                    await self.client.delete(*keys)
                if cursor == 0:
                    break

        self._system_aggregators = self._make_system_aggregators()
