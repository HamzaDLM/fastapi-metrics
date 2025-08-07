import random
import time

import uvicorn
from fastapi import FastAPI

from fastapi_metrics_dashboard import FastAPIMetricsDashboard
from fastapi_metrics_dashboard.decorator import exclude_from_metrics
import gc

app = FastAPI()

FastAPIMetricsDashboard.init(app)


@app.get("/")
def index():
    return "ok"


@app.put("/ping")
def ping():
    time.sleep(1)
    return "pong"


@app.patch("/patch")
def patch():
    return "ua"


@app.get("/fail")
def fail():
    return 0 / 0


@app.get("/calculation")
def calculation():
    big_list = []
    start_time = time.time()
    while time.time() - start_time < 15:
        _ = sum(random.random() ** 2 for _ in range(10000))
        big_list.append([random.random()] * 10000)
        time.sleep(0.01)

    gc.collect()
    return {"done": True}


@app.get("/sensitive")
@exclude_from_metrics
def sensitive():
    return "sensitive"


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
