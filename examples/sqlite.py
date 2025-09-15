from fastapi import FastAPI

from fastapi_metrics import Config, FastAPIMetrics
from fastapi_metrics.backends.sqlite import SQLiteMetricsStore

app = FastAPI()

FastAPIMetrics.init(
    app,
    SQLiteMetricsStore(db_path="metrics.db"),
    config=Config(),
)


@app.get("/")
def index():
    return "ok"
