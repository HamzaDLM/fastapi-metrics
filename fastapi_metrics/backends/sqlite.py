import json

try:
    import sqlite3
except ImportError as e:
    raise ImportError(
        "SQLite backend requires 'sqlite3', which is not available in your Python build."
        "Reinstall Python with SQLite support."
    ) from e

import sqlite3

import time
from collections import defaultdict

from fastapi_metrics.backends.base import MetricsStore


class SQLiteMetricsStore(MetricsStore):
    """
    SQLite implementation of `MetricsStore` for request and system metrics.

    Metrics are stored in multiple time-bucket resolutions.
    with TTL-based cleanup to prevent unbounded memory growth.

    Attributes:
        db_path (string): SQLite db path.
        _ttl_seconds (int): Time-to-live (in seconds) for stored metrics.
    """

    def __init__(self, db_path: str = "metrics.db", ttl_seconds: int | None = None):
        super().__init__()
        self.ttl_seconds = ttl_seconds
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(
            """
        CREATE TABLE IF NOT EXISTS system_metrics (
            bucket_size INTEGER,
            bucket_ts INTEGER,
            key TEXT,
            data TEXT,
            PRIMARY KEY (bucket_size, bucket_ts, key)
        )"""
        )
        self.conn.execute(
            """
        CREATE TABLE IF NOT EXISTS request_metrics (
            bucket_size INTEGER,
            bucket_ts INTEGER,
            path TEXT,
            data TEXT,
            PRIMARY KEY (bucket_size, bucket_ts, path)
        )"""
        )
        self.conn.commit()

    @property
    def bucket_sizes(self) -> list[int]:
        """List of supported bucket sizes (in seconds)."""
        return [60, 300, 900, 1800]

    def record_request_metrics(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        """
        Record request-level metrics into all bucket resolutions.

        Format:
            bucket_size | bucket_timestamp | path | data

        Args:
            path: The request path (route).
            duration: Request latency in seconds.
            status_code: HTTP status code of the response.
            method: HTTP method of the request (GET, POST, etc.).
        """
        now = int(time.time())
        for bucket_size in self.bucket_sizes:
            bucket_ts = (now // bucket_size) * bucket_size

            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT data FROM request_metrics 
                WHERE bucket_size=? AND bucket_ts=? AND path=?
            """,
                (bucket_size, bucket_ts, path),
            )
            row = cur.fetchone()

            if row:
                route_stats = json.loads(row[0])
            else:
                route_stats = {
                    "latencies": [],
                    "count": 0,
                    "errors": 0,
                    "status_codes": {},
                    "methods": {},
                    "rw_count": {},
                }

            route_stats["latencies"].append(duration)
            route_stats["count"] += 1
            if 400 <= status_code < 600:
                route_stats["errors"] += 1

            group = f"{status_code // 100}XX"
            route_stats["status_codes"][group] = (
                route_stats["status_codes"].get(group, 0) + 1
            )
            route_stats["methods"][method.upper()] = (
                route_stats["methods"].get(method.upper(), 0) + 1
            )

            if "read" not in route_stats["rw_count"]:
                route_stats["rw_count"]["read"] = 0
            if "write" not in route_stats["rw_count"]:
                route_stats["rw_count"]["write"] = 0

            rw_key = "read" if method.upper() in ("GET", "HEAD", "OPTIONS") else "write"
            route_stats["rw_count"][rw_key] = route_stats["rw_count"].get(rw_key, 0) + 1

            cur.execute(
                """
                INSERT INTO request_metrics (bucket_size, bucket_ts, path, data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(bucket_size, bucket_ts, path) DO UPDATE SET data=excluded.data
            """,
                (bucket_size, bucket_ts, path, json.dumps(route_stats)),
            )
        self.conn.commit()

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
        result = defaultdict(dict)
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT bucket_ts, path, data 
            FROM request_metrics 
            WHERE bucket_size=? AND bucket_ts BETWEEN ? AND ?
        """,
            (bucket_size, ts_from, ts_to),
        )
        for bucket_ts, path, data in cur.fetchall():
            result[bucket_ts][path] = json.loads(data)
        return result

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
        bucket_ts = (data["timestamp"] // bucket_size) * bucket_size
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO system_metrics (bucket_size, bucket_ts, key, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bucket_size, bucket_ts, key) DO UPDATE SET data=excluded.data
        """,
            (bucket_size, bucket_ts, key, json.dumps(data)),
        )
        self.conn.commit()

    def get_system_metrics_series(
        self, bucket_size: int, ts_from: int, ts_to: int
    ) -> dict[str, list[dict]]:
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
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT bucket_ts, key, data FROM system_metrics
            WHERE bucket_size=? AND bucket_ts BETWEEN ? AND ?
        """,
            (bucket_size, ts_from, ts_to),
        )
        for _, key, data in cur.fetchall():
            data_points[key].append(json.loads(data))
        return data_points

    def _cleanup_expired_ttl(self) -> None:
        """
        Removes old request and system buckets whose age exceeds `_ttl_seconds`.
        """
        if self.ttl_seconds is None:
            return

        cutoff_ts = int(time.time()) - self.ttl_seconds
        cur = self.conn.cursor()

        cur.execute("DELETE FROM request_metrics WHERE bucket_ts < ?", (cutoff_ts,))
        cur.execute("DELETE FROM system_metrics WHERE bucket_ts < ?", (cutoff_ts,))

        self.conn.commit()

    def reset(self) -> None:
        """
        Reset all metrics.

        Clears request buckets, system buckets, and re-initializes
        system aggregators to their default state.
        """
        self.conn.execute("DELETE FROM request_metrics")
        self.conn.execute("DELETE FROM system_metrics")
        self.conn.commit()

        self._system_aggregators = self._make_system_aggregators()
