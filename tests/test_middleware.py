import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fastapi_metrics.middleware import MetricsMiddleware
from fastapi_metrics.backends.in_memory import InMemoryMetricsStore


def create_test_app():
    store = InMemoryMetricsStore()

    app = FastAPI()
    app.add_middleware(MetricsMiddleware, store=store)

    @app.get("/ping")
    async def ping():
        return {"msg": "pong"}

    return app, store


@pytest.mark.asyncio
async def test_metrics_collected():
    app, store = create_test_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/ping")

    metrics = await store.get_metrics()
    print(metrics)
    assert False
