from fastapi_metrics_dashboard.backends.in_memory import InMemoryMetricsStore

_metrics_store = None


def get_metrics_store():
    global _metrics_store
    if _metrics_store is None:
        # TODO handle other cases
        _metrics_store = InMemoryMetricsStore()
    return _metrics_store
