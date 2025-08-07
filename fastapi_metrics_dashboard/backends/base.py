from abc import ABC, abstractmethod
from typing import Dict, Any


class MetricsStore(ABC):
    @abstractmethod
    async def record_request_log(
        self, path: str, duration: float, status_code: int, method: str
    ) -> None:
        pass

    @abstractmethod
    async def record_system_metrics(self) -> None:
        pass

    @abstractmethod
    async def get_metrics(self, ts_from: int, ts_to: int) -> Dict[str, Any]:
        pass


"""
===================REQUEST/LATENCY/ERROR METRICS TABLE (per route)============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "status": 200, path: "route1", latency: 3.99, "method": "Get"...},
  ...
]

# Pre-aggregated per-X time structure (STORED/SERVED)
[
    {
        "path": "route1", 
        "p99_latency": 200, 
        "p99_max_latency": 300,
        "request_per_minute": 2
        "max_request_per_minute": 2
        "error_count": 0,
        "error_rate": 0.0,
        "status_codes": {
            "2XX": 100,
            "4XX": 0,
            "5XX": 0,
        }
    },
    ...
]

===================REQUEST METRICS (RPM per status code)============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "status": 200, path: "route1", latency: 3.99, "method": "Get"...},
  ...
]

# Pre-aggregated per-X time structure (STORED)
{
    1720000000: {
        "2XX": 134,
        "4XX": 4,
        "5XX": 2,
    },
    ...
}

# Apex final form (SERVED)
[
    {
        name: "2XX",
        data: [["01:00", 120], ["01:01", 122], ...]
    },
    ...
]

===================REQUEST METRICS (read/write per time)============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "status": 200, path: "route1", latency: 3.99, "method": "Get" ...},
  ...
]

# Pre-aggregated per-X time structure (STORED)
{
    1720000000: {
        "write": 134,
        "read": 4,
    },
    ...
}

# Apex final form (SERVED)
[
    {
        name: "Read",
        data: [["01:00", 120], ["01:01", 122], ...]
    },
    {
        name: "Write",
        data: [["01:00", 120], ["01:01", 122], ...]
    },
]

===================REQUEST METRICS (top 5 transactions)============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "status": 200, path: "route1", latency: 3.99, "method": "Get" ...},
  ...
]

# Pre-aggregated per-X time structure (STORED)
{
    1720000000: {
        "route1": 13,
        "route2": 4,
    },
    ...
}

# Final form (SERVED)
{
    "route1": 400,
    "route2": 320,
    ...
}

===================REQUEST METRICS (method counts)============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "status": 200, path: "route1", latency: 3.99, "method": "Get" ...},
  ...
]

# Pre-aggregated per-X time structure (STORED)
{
    1720000000: {
        "Get": 13,
        "Post": 4,
        "Put": 4,
    },
    ...
}

# Final form (SERVED)
{
    "Get": 400,
    "Put": 320,
    ...
}

======================LATENCY METRICS=============================

# Raw log format (COLLECTED)
[
  {"timestamp": 1720000000, "latency": 200, ...},
  ...
]

# Pre-aggregated per-minute structure (STORED)
{
    1720000000: {
        "route_name": 0.889,
        "route_name": 0.889,
        ...
    },
    ...
}

# Apex final form (SERVED)
[
    {
        name: "route_name",
        data: [["01:00", 120], ["01:01", 122], ...]
    },
    ...
]

======================SYSTEM METRICS=============================

# Raw log format
[
  {"timestamp": 1720000000, "status": 200, ...},
  ...
]

# Pre-aggregated per-minute structure
{
    1720000000: {
        "cpu_percent": 134,
        "memory_percent": 4,
        ...
    },
}

# Apex final form
[
    {
        name: "CPU percent",
        data: [["01:00", 120], ["01:01", 122], ...]
    },
     ...
]

========================================================================

What resolution is best?

saved with 5s buckets

Time range      - 	Bucket duration	    Total data points (per metric)
Last 1 hour     -	10s	                - 360
Last 6 hours    -	1m	                - 360
Last 24 hours   -	1m	                - 1440
Last 7 days	    -	5m                  - ~2,000
"""
