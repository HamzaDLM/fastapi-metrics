import redis.asyncio as async_redis
from fastapi import FastAPI

from fastapi_metrics import Config, FastAPIMetrics
from fastapi_metrics.backends.redis import AsyncRedisMetricsStore

app = FastAPI()

redis_client = async_redis.Redis(host="localhost", port=6379, db=0)

FastAPIMetrics.init(
    app,
    AsyncRedisMetricsStore(redis_client),
    config=Config(),
)


@app.get("/")
def index():
    return "ok"
