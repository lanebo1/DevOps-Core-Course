"""
DevOps Info Service
Main application module (FastAPI).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
import uvicorn

# Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelname", "levelno", "lineno",
                "message", "module", "msecs", "msg", "name", "pathname",
                "process", "processName", "relativeCreated", "stack_info",
                "thread", "threadName",
            } and not key.startswith("_"):
                log_obj[key] = value
        return json.dumps(log_obj, default=str)


handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.root.setLevel(logging.INFO)
logging.root.handlers = [handler]
logger = logging.getLogger("devops-info-service")

# Application start time
START_TIME = datetime.now(timezone.utc)

http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
)

devops_info_endpoint_calls = Counter(
    "devops_info_endpoint_calls_total",
    "Total calls per named endpoint",
    ["endpoint"],
)

system_info_collection_seconds = Histogram(
    "devops_info_system_collection_seconds",
    "Time spent collecting system information",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05],
)

# ---------------------------------------------------------------------------

app = FastAPI(title="DevOps Info Service", version="1.0.0")


@app.middleware("http")
async def log_and_instrument_requests(request: Request, call_next):
    path = request.url.path

    if path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "HTTP request",
        extra={
            "method": request.method,
            "path": path,
            "client_ip": client_ip,
        },
    )

    http_requests_in_progress.inc()
    try:
        response = await call_next(request)
    finally:
        http_requests_in_progress.dec()

    duration = time.perf_counter() - start
    duration_ms = round(duration * 1000, 2)
    status = str(response.status_code)

    http_requests_total.labels(
        method=request.method,
        endpoint=path,
        status=status,
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=path,
    ).observe(duration)

    logger.info(
        "HTTP response",
        extra={
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip,
        },
    )
    return response


def get_uptime() -> dict:
    """Return uptime in seconds and a human-readable format."""
    now = datetime.now(timezone.utc)
    delta = now - START_TIME
    seconds = int(delta.total_seconds())
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return {"seconds": seconds, "human": f"{hours} hours, {minutes} minutes"}


def get_system_info() -> dict:
    """Collect system information."""
    with system_info_collection_seconds.time():
        return {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
        }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not Found",
                "message": "Endpoint does not exist",
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "message": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
        },
    )


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def index(request: Request):
    """Main endpoint - service and system information."""
    devops_info_endpoint_calls.labels(endpoint="/").inc()
    uptime = get_uptime()
    now = datetime.now(timezone.utc)

    client_host = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    return {
        "service": {
            "name": "devops-info-service",
            "version": "1.0.0",
            "description": "DevOps course info service",
            "framework": "FastAPI",
        },
        "system": get_system_info(),
        "runtime": {
            "uptime_seconds": uptime["seconds"],
            "uptime_human": uptime["human"],
            "current_time": now.isoformat(),
            "timezone": "UTC",
        },
        "request": {
            "client_ip": client_host,
            "user_agent": user_agent,
            "method": request.method,
            "path": request.url.path,
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "Service information"},
            {"path": "/health", "method": "GET", "description": "Health check"},
        ],
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    devops_info_endpoint_calls.labels(endpoint="/health").inc()
    uptime = get_uptime()
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime["seconds"],
    }


if __name__ == "__main__":
    logger.info(
        "Starting DevOps Info Service",
        extra={"host": HOST, "port": PORT, "debug": DEBUG},
    )
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
