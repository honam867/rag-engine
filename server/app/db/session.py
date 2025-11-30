from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from server.app.core.config import get_settings

_settings = get_settings()

def _ensure_async_driver(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


engine: AsyncEngine = create_async_engine(
    _ensure_async_driver(_settings.database.db_url),
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args={
        # Tắt prepared statements để tương thích với Supabase Transaction Pooler (Port 6543)
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda *args: "",
    },
)
async_session = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
