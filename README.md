# fastapi-metrics

![Dashboard Screenshot](https://github.com/HamzaDLM/fastapi-metrics/blob/main/fastapi_metrics/static/bg.png?raw=true)

## Introduction

`fastapi-metrics` is a FastAPI extension for application performance monitoring.
It tracks request and system metrics using lightweight middleware.
Metrics can be stored in in-memory, SQLite, or Redis backends and visualized in a built-in dashboard UI.

## Who is it for?

- Developers who want a metrics dashboard without running a full Prometheus + Grafana stack.
- Indie devs or small teams running single-instance FastAPI backends who just need lightweight insights.

## Features

- 🚀 Zero-config FastAPI middleware
- 🗄 Multiple storage backends: in-memory, SQLite, Redis
- 💻 Built-in dashboard UI with charts
- ⚡ Lightweight & async-first design
- 🔌 Configurable retention, bucket sizes, and cleanup

## Installation

```shell
> pip install fastapi-metrics
```

Optional dependencies:

```shell
> pip install "fastapi-metrics[redis]"
> pip install "fastapi-metrics[aiosqlite]"
```

## Quick Start

Check the `examples` folder for more.

```python
from fastapi import FastAPI
from fastapi_metrics import FastAPIMetrics, Config
from fastapi_metrics.backends.memory import InMemoryMetricsStore

app = FastAPI()

FastAPIMetrics.init(
    app,
    InMemoryMetricsStore(),
    config=Config(),
)

@app.get("/")
def index():
    return "ok"
```

Visit `/metrics` to view the UI.

## Backends

#### In-Memory (default)

```python
from fastapi_metrics.backends.memory import InMemoryMetricsStore
store = InMemoryMetricsStore()
```

#### Redis

```python
from fastapi_metrics.backends.redis import RedisMetricsStore

# sync
import redis

redis_client = redis.Redis(host="localhost", port=6379, db=0)
store = RedisMetricsStore(redis_client)

# async
import redis.asyncio as async_redis

async_redis_client = async_redis.Redis(host="localhost", port=6379, db=0)
async_store = AsyncRedisMetricsStore(async_redis_client),
```

#### SQLite

```python
from fastapi_metrics.backends.sqlite import SQLiteMetricsStore
store = SQLiteMetricsStore("metrics.db")
```

## Development

```shell
git clone https://github.com/HamzaDLM/fastapi-metrics
cd fastapi-metrics
uv sync
uv run pytest
```

## License

This project is licensed under the Apache-2.0 License.
