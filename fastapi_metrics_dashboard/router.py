from fastapi import APIRouter
from fastapi.responses import JSONResponse

from fastapi_metrics_dashboard.store import get_metrics_store
import time
from fastapi_metrics_dashboard.logger import logger
from fastapi_metrics_dashboard.utils import ts_to_readable

metrics_router = APIRouter(prefix="/metrics")


@metrics_router.get("/json", status_code=200)
async def get_metrics(ts_from: int, ts_to: int | None = None):
    logger.debug(
        f"ROUTER: get metrics {ts_to_readable(ts_from)} to {ts_to_readable(ts_to)}"
    )

    if ts_to is None:
        ts_to = int(time.time())

    data = await get_metrics_store().get_metrics(ts_from=ts_from, ts_to=ts_to)
    return JSONResponse(content=data)


@metrics_router.get("/table_overview", status_code=200)
async def get_table_overview(
    ts_from: int,
    ts_to: int | None = None,
):
    logger.debug(
        f"ROUTER: get overview table, from:{ts_to_readable(ts_from)} to:{ts_to_readable(ts_to)}"
    )

    if ts_to is None:
        ts_to = int(time.time())

    data = get_metrics_store().get_table_overview(ts_from, ts_to)
    return JSONResponse(content=data)


@metrics_router.delete("/reset", status_code=204)
def reset_store():
    logger.debug("ROUTER: reset store")
    get_metrics_store().reset()
    return JSONResponse(content="metrics store reset!")
