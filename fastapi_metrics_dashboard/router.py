import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from fastapi_metrics_dashboard.config import Config
from fastapi_metrics_dashboard.backends.base import MetricsStore
from fastapi_metrics_dashboard.logger import logger
from fastapi_metrics_dashboard.utils import ts_to_readable, pin_auth_basic


def get_metrics_router(store: MetricsStore, config: Config) -> APIRouter:
    metrics_router = APIRouter(
        prefix="/metrics", dependencies=[Depends(pin_auth_basic(config))]
    )

    @metrics_router.get(
        "/config-b887e852-bd12-41f2-b057-1bd31eb5443e", include_in_schema=True
    )
    async def get_config():
        return {"pin_required": config.ui_pin}

    @metrics_router.get(
        f"{config.custom_path}/json",
        status_code=200,
        include_in_schema=config.include_in_openapi,
    )
    async def get_metrics(ts_from: int, ts_to: int | None = None):
        logger.debug(
            f"ROUTER: get metrics {ts_to_readable(ts_from)} to {ts_to_readable(ts_to)}"
        )

        if ts_to is None:
            ts_to = int(time.time())

        data = store.get_metrics(ts_from=ts_from, ts_to=ts_to)
        return JSONResponse(content=data)

    @metrics_router.get(
        f"{config.custom_path}/table_overview",
        status_code=200,
        include_in_schema=config.include_in_openapi,
    )
    async def get_table_overview(
        ts_from: int,
        ts_to: int | None = None,
    ):
        logger.debug(
            f"ROUTER: get overview table, from:{ts_to_readable(ts_from)} to:{ts_to_readable(ts_to)}"
        )

        if ts_to is None:
            ts_to = int(time.time())

        data = store.get_table_overview(ts_from, ts_to)
        return JSONResponse(content=data)

    @metrics_router.delete(
        f"{config.custom_path}/reset",
        status_code=204,
        include_in_schema=config.include_in_openapi,
    )
    async def reset_store():
        logger.debug("ROUTER: reset store")
        store.reset()
        return JSONResponse(content="metrics store reset!")

    return metrics_router
