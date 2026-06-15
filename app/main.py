from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import connection, health, migration, schema
from app.core.config import settings
from app.core.database import dispose_engine
from app.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


# ── Custom exceptions ──────────────────────────────────────────────────────────

class ConnectionError(Exception):  # noqa: A001
    pass


class SchemaError(Exception):
    pass


class MigrationError(Exception):
    pass


class ProviderError(Exception):
    pass


# ── App factory ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(debug=settings.DEBUG)
    logger.info("DataBridge starting", version=settings.APP_VERSION, env=settings.ENVIRONMENT)
    yield
    await dispose_engine()
    logger.info("DataBridge shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "DataBridge — production-grade database migration platform. "
        "Migrate data between PostgreSQL, MySQL, and SQLite with full "
        "schema mapping, batch processing, and real-time progress tracking."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handlers ──────────────────────────────────────────────────

def _error_response(status_code: int, error: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": error, "detail": str(detail) if detail else None},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return _error_response(400, "Validation error", exc)


@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError) -> JSONResponse:
    return _error_response(503, "Connection failed", exc)


@app.exception_handler(SchemaError)
async def schema_error_handler(request: Request, exc: SchemaError) -> JSONResponse:
    return _error_response(422, "Schema error", exc)


@app.exception_handler(MigrationError)
async def migration_error_handler(request: Request, exc: MigrationError) -> JSONResponse:
    return _error_response(500, "Migration error", exc)


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    return _error_response(500, "Provider error", exc)


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError) -> JSONResponse:
    return _error_response(501, "Not implemented", exc)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception", path=request.url.path, error=str(exc), exc_info=exc)
    return _error_response(500, "Internal server error")


# ── Routes ─────────────────────────────────────────────────────────────────────

API_PREFIX = "/api"

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(connection.router, prefix=API_PREFIX)
app.include_router(schema.router, prefix=API_PREFIX)
app.include_router(migration.router, prefix=API_PREFIX)
