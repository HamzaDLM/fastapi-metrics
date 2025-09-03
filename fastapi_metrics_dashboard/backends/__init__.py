from typing import DefaultDict, Literal, TypedDict


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
    status_codes: DefaultDict[str, int]
    methods: DefaultDict[str, int]
    rw_count: DefaultDict[Literal["read", "write"], int]
