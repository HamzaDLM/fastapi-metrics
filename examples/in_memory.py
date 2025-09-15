from fastapi import FastAPI

from fastapi_metrics import FastAPIMetrics, Config

from fastapi_metrics.backends.in_memory import InMemoryMetricsStore


app = FastAPI()

FastAPIMetrics.init(
    app,
    InMemoryMetricsStore(),
    config=Config(),
)


@app.get("/")
def index():
    return "ok"
