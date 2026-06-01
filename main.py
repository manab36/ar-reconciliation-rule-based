import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# from app.api.ar_reconciliation_records import router as ar_reconciliation_records_router
# from app.api.workflows import router as workflows_router
from app.core.database import init_db
from app.routes import ar_reconciliation, health

# from app.services.ar_reconciliation_pipeline import pipeline_runner
# from app.api.dashboard import router as dashboard_router


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


# Register routers with tags
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(
    ar_reconciliation.router, prefix="/ar_records", tags=["ar_reconciliation_records"]
)
# app.include_router(pipeline_runner.router, prefix="/ar_pipeline", tags=["run_ar_pipeline"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
