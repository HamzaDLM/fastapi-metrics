import random
import time

import uvicorn
from fastapi import FastAPI

from fastapi_metrics_dashboard import FastAPIMetricsDashboard, Config
from fastapi_metrics_dashboard.decorator import exclude_from_metrics

from fastapi_metrics_dashboard.backends.in_memory import InMemoryMetricsStore

# from fastapi_metrics_dashboard.backends.redis import RedisMetricsStore
# from fastapi_metrics_dashboard.backends.sqlite import SQLiteMetricsStore
# import redis
# import redis.asyncio as async_redis
# import sqlite3

app = FastAPI()

in_memory_store = InMemoryMetricsStore()

# sync redis client
# redis_client = redis.Redis()
# redis_store = RedisMetricsStore(redis_client)

# # async redis client
# redis_client = async_redis.Redis()
# redis_store = RedisMetricsStore(redis_client)

# # sync sqlite client
# sqlite_client = sqlite3.connect("tutorial.db")
# sqlite_store = SQLiteMetricsStore(sqlite_client)
# async sqlite client


FastAPIMetricsDashboard.init(
    app, in_memory_store, config=Config(ui_pin=1997, include_in_openapi=True)
)


@app.get("/")
def index():
    return "ok"


@app.get("/calculation")
def calculation():
    big_list = []
    start_time = time.time()
    while time.time() - start_time < 15:
        _ = sum(random.random() ** 2 for _ in range(10000))
        big_list.append([random.random()] * 100000)
        time.sleep(0.01)

    return {"done": True}


@exclude_from_metrics
@app.get("/sensitive")
def sensitive():
    return "sensitive"


if __name__ == "__main__":
    uvicorn.run("main:app", reload=False, log_level="debug")
