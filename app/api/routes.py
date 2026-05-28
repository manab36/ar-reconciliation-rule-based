import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.submissions import router as submissions_router
from app.api.workflows import router as workflows_router
from app.core.database import init_db


def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info("database_initialized")
    yield


app = FastAPI(
    title="AR Reconciliation Workflow Engine",
    description="Async workflow engine for Accounts Receivable reconciliation with retry, resume, and parallel execution.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins for POC (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_error",
        path=request.url.path,
        error=str(exc),
        exc_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Register routers
app.include_router(health_router)
app.include_router(submissions_router)
app.include_router(workflows_router)
app.include_router(dashboard_router)
