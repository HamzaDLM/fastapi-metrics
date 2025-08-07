import asyncio
import os
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fastapi_metrics_dashboard.middleware import MetricsMiddleware
from fastapi_metrics_dashboard.router import metrics_router
from fastapi_metrics_dashboard.store import get_metrics_store

__all__ = ["MetricsMiddleware", "metrics_router"]


class FastAPIMetricsDashboard:
    _initialized_apps: ClassVar[set[int]] = set()
    _tasks: ClassVar[dict[int, asyncio.Task]] = {}
    _sys_metrics_sampling_interval: ClassVar[int] = 5  # seconds
    _enable_dashboard_ui: ClassVar[bool] = True
    _dashboard_ui_path: ClassVar[str] = "/metrics"
    # _retention_rate:

    @classmethod
    def init(cls, app: FastAPI) -> None:
        if id(app) in cls._initialized_apps:
            return

        if not hasattr(app.router, "lifespan_context"):
            raise RuntimeError(
                "fastapi app instance must be created before calling FastAPIMetricsDashboard.init(app)"
            )

        cls._setup_lifepan(app)
        cls._register_routes(app)

        cls._initialized_apps.add(id(app))

    @classmethod
    def _setup_lifepan(cls, app: FastAPI):
        original_lifespan = getattr(app.router, "lifespan_context", None)

        @asynccontextmanager
        async def injected_lifespan(app: FastAPI):
            cls._tasks[id(app)] = asyncio.create_task(cls._collect_sys_metrics_loop())

            if original_lifespan:
                async with original_lifespan(app):
                    # Startup
                    yield
                    # Shutdown
            else:
                yield

            task = cls._tasks.pop(id(app), None)

            if task:
                task.cancel()

            try:
                await cls._tasks[id(app)]
            except asyncio.CancelledError:
                pass

        app.router.lifespan_context = injected_lifespan

    @classmethod
    def _register_routes(cls, app: FastAPI):
        app.add_middleware(MetricsMiddleware)
        app.include_router(metrics_router, tags=["fastapi dashboard metrics"])
        if cls._enable_dashboard_ui:
            app.mount(
                cls._dashboard_ui_path,
                StaticFiles(
                    directory=os.path.join(
                        os.path.dirname(__file__), "static", "frontend"
                    ),
                    html=True,
                ),
                name="metrics",
            )

    @classmethod
    async def _collect_sys_metrics_loop(cls):
        while True:
            store = get_metrics_store()
            await store.record_system_metrics()
            await asyncio.sleep(cls._sys_metrics_sampling_interval)

    @classmethod
    async def _cleanup(cls):
        pass
