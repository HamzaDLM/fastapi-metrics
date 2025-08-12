import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fastapi_metrics_dashboard.store import get_metrics_store


class MetricsMiddleware(BaseHTTPMiddleware):
    # TODO exclude metrics paths by default
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        status_code = 500

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time

            path = request.url.path
            method = request.method

            store = get_metrics_store()

            await store.record_request_metrics(path, duration, status_code, method)

        return response
