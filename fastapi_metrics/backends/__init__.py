from fastapi_metrics.backends.in_memory import InMemoryMetricsStore

__all__ = ["InMemoryMetricsStore"]

try:
    from fastapi_metrics.backends.redis import RedisMetricsStore, AsyncMetricsStore
except ImportError:
    pass
else:
    __all__ += ["RedisMetricsStore", "AsyncMetricsStore"]

try:
    from fastapi_metrics.backends.sqlite import SQLiteMetricsStore
except ImportError:
    pass
else:
    __all__ += ["SQLiteMetricsStore"]
