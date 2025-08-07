from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from fastapi_metrics_dashboard.store import get_metrics_store
import time

metrics_router = APIRouter(prefix="/metrics")


@metrics_router.get("/json")
async def get_metrics(ts_from: int = Query(...), ts_to: int | None = Query(None)):
    store = get_metrics_store()

    if ts_to is None:
        ts_to = int(time.time())

    data = await store.get_metrics(ts_from=ts_from, ts_to=ts_to)
    return JSONResponse(content=data)
