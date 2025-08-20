from fastapi_metrics_dashboard.backends.base import MetricsStore


class RedisMetricsStore(MetricsStore):
    def __init__(
        self,
        host,
        port,
        db,
        password,
    ):
        pass
