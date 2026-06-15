from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# libpq query params that asyncpg's driver does not accept and that must be
# stripped from the URL (managed Postgres providers like Neon include them).
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}


def build_async_url(url: str) -> tuple[str, dict]:
    """Normalize a Postgres URL for SQLAlchemy + asyncpg.

    Returns the async URL (with libpq-only params stripped) and the
    ``connect_args`` needed to honor any TLS requirement from the original URL.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    params = parse_qsl(parts.query)
    requires_ssl = any(
        k == "sslmode" and v in ("require", "verify-ca", "verify-full")
        for k, v in params
    )
    kept = [(k, v) for k, v in params if k not in _LIBPQ_ONLY_PARAMS]
    clean_url = urlunsplit(parts._replace(query=urlencode(kept)))

    connect_args = {"ssl": True} if requires_ssl else {}
    return clean_url, connect_args


_async_url, _connect_args = build_async_url(settings.DATABASE_URL)

_engine = create_async_engine(
    _async_url,
    connect_args=_connect_args,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables defined via the ORM (used in testing / initial setup)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    await _engine.dispose()
