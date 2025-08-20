import asyncio
import os
from contextlib import asynccontextmanager
from typing import ClassVar

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fastapi_metrics_dashboard.middleware import MetricsMiddleware
from fastapi_metrics_dashboard.router import metrics_router
from fastapi_metrics_dashboard.store import get_metrics_store
from fastapi_metrics_dashboard.backends.in_memory import InMemoryMetricsStore
from fastapi_metrics_dashboard.backends.redis import RedisMetricsStore
from fastapi_metrics_dashboard.backends.sqlite import SQLiteMetricsStore

__all__ = ["MetricsMiddleware", "metrics_router"]

# ok talking about my library fastapi-metrics-dashboard, lets refactor things, for the moment I did all the logic in in_memory.py, but I wanna move shared logic into base.py and then do specific implementations and appropriate bucket sizes/retention time per memory type in_memory/redis/sqlite


class FastAPIMetricsDashboard:
    _initialized_apps: ClassVar[set[int]] = set()
    _tasks: ClassVar[dict[int, asyncio.Task]] = {}
    _sys_metrics_sampling_interval: ClassVar[int] = 5  # seconds
    _enable_dashboard_ui: ClassVar[bool] = True
    _dashboard_ui_path: ClassVar[str] = "/metrics"
    _cleanup_expired_rate: ClassVar[int] = 60 * 60  # seconds
    _routes_ignored: ClassVar[list[str]] = []

    @classmethod
    def init(
        cls,
        app: FastAPI,
        store: InMemoryMetricsStore | RedisMetricsStore | SQLiteMetricsStore,
        config: dict,
    ) -> None:
        print("store:", type(store))
        print("config:", config)
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
            cls._tasks[id(app)] = asyncio.create_task(cls._cleanup())

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
        while True:
            get_metrics_store()._cleanup_expired_ttl()
            await asyncio.sleep(cls._cleanup_expired_rate)
