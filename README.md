# fastapi-metrics-dashboard

## Introduction

`fastapi-metrics-dashboard` is a FastAPI extension that tracks different metrics like request count, latency, and status codes using lightweight middleware. It provides a built-in dashboard UI and supports multiple storage backends, including in-memory, SQLite, and Redis.

## Features

- supports: redis, sqlite and in_memory (default) stores.
- comes with useful decorators like the `@skip_router` and more...
- customizable frontend theme by providing a css file
- provides data in form of json
- auth

## Requirements

- Fastapi

## Installation

```shell
> pip install fastapi-metrics-dashboard
```

or

```shell
> pip install "fastapi-metrics-dashboard[redis]"
```

or

```shell
> pip install "fastapi-metrics-dashboard[sqlite3]"
```

## Quick Start

Check the `examples` folder for more.

```
from fastapi import FastAPI

from fastapi_metrics_dashboard import FastAPIMetricsDashboard
from fastapi_metrics_dashboard.decorator import exclude_from_metrics


app = FastAPI()

FastAPIMetricsDashboard().init(app)


@app.get("/ping")
def ping():
    return "pong"


@app.get("/sentitive")
@exclude_from_metrics
def sensitive():
    return "sensitive"
```

## Decorators

table

## License

This project is licensed under the Apache-2.0 License.
