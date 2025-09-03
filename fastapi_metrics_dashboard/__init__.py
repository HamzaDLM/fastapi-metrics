import asyncio
import inspect
import os
from contextlib import asynccontextmanager
from typing import ClassVar, cast

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fastapi_metrics_dashboard.backends.base import AsyncMetricsStore, MetricsStore
from fastapi_metrics_dashboard.backends.in_memory import InMemoryMetricsStore
from fastapi_metrics_dashboard.config import Config
from fastapi_metrics_dashboard.logger import logger
from fastapi_metrics_dashboard.middleware import (
    AsyncMetricsMiddleware,
    MetricsMiddleware,
)
from fastapi_metrics_dashboard.router import (
    get_async_metrics_router,
    get_metrics_router,
)

# __all__ = ["MetricsMiddleware", "metrics_router"]


class FastAPIMetricsDashboard:
    _initialized_apps: ClassVar[set[int]] = set()
    _tasks: ClassVar[dict[int, list[asyncio.Task]]] = {}
    _sys_metrics_sampling_interval: ClassVar[int] = 5  # seconds
    _cleanup_expired_rate: ClassVar[int] = 60 * 60  # seconds

    @classmethod
    def init(
        cls,
        app: FastAPI,
        store: MetricsStore | AsyncMetricsStore,
        config: Config | None = None,
    ) -> None:
        if id(app) in cls._initialized_apps:
            return

        if not hasattr(app.router, "lifespan_context"):
            raise RuntimeError(
                "fastapi app instance must be created before calling FastAPIMetricsDashboard.init(app)"
            )

        cls.config = config or Config()
        cls.store = store or InMemoryMetricsStore()

        cls._setup_lifepan(app)

        if isinstance(cls.store, AsyncMetricsStore):
            cls._async_register_routes(app)
        else:
            cls._register_routes(app)

        cls._initialized_apps.add(id(app))

    @classmethod
    def _setup_lifepan(cls, app: FastAPI):
        original_lifespan = getattr(app.router, "lifespan_context", None)

        @asynccontextmanager
        async def injected_lifespan(app: FastAPI):
            app_id = id(app)
            tasks = []
            tasks.append(asyncio.create_task(cls._collect_sys_metrics_loop()))
            tasks.append(asyncio.create_task(cls._cleanup()))
            cls._tasks[app_id] = tasks

            logger.debug(f"MAIN: Starting lifespan for app {app_id}")

            try:
                if original_lifespan:
                    async with original_lifespan(app):
                        logger.debug("MAIN: App is running with original lifespan...")
                        yield
                        logger.debug("MAIN: Original lifespan shutting down...")
                else:
                    logger.debug("MAIN: App is running...")
                    yield
                    logger.debug("MAIN: App shutting down...")
            finally:
                logger.debug(f"MAIN: Cleaning up lifespan for app {app_id}")
                for task in cls._tasks.pop(app_id, []):
                    logger.debug(f"MAIN: Cancelling task: {task.get_name()}")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.debug("MAIN: Task cancelled successfully")
                        pass
                logger.debug(f"MAIN: Cleaned up tasks for app {app_id}")

        app.router.lifespan_context = injected_lifespan

    @classmethod
    def _register_routes(cls, app: FastAPI):
        app.add_middleware(
            MetricsMiddleware, store=cast(MetricsStore, cls.store), config=cls.config
        )
        app.include_router(
            get_metrics_router(cast(MetricsStore, cls.store), cls.config),
            tags=["fastapi dashboard metrics"],
        )

        if cls.config.enable_dashboard_ui:
            app.mount(
                cls.config.custom_path,
                StaticFiles(
                    directory=os.path.join(
                        os.path.dirname(__file__), "static", "frontend"
                    ),
                    html=True,
                ),
                name="metrics",
            )

    @classmethod
    def _async_register_routes(cls, app: FastAPI):
        app.add_middleware(
            AsyncMetricsMiddleware,
            store=cast(AsyncMetricsStore, cls.store),
            config=cls.config,
        )
        app.include_router(
            get_async_metrics_router(cast(AsyncMetricsStore, cls.store), cls.config),
            tags=["fastapi dashboard metrics"],
        )
        if cls.config.enable_dashboard_ui:
            app.mount(
                cls.config.custom_path,
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
            result = cls.store.record_system_metrics()
            if inspect.isawaitable(result):
                await result
            await asyncio.sleep(cls._sys_metrics_sampling_interval)

    @classmethod
    async def _cleanup(cls):
        while True:
            result = cls.store._cleanup_expired_ttl()
            if inspect.isawaitable(result):
                await result
            await asyncio.sleep(cls._cleanup_expired_rate)
