from fastapi import FastAPI
import sqlalchemy as sa

from server.app.api.routes import conversations, documents, me, messages, workspaces
from server.app.core.logging import get_logger, setup_logging
from server.app.db.session import engine
from server.app.schemas.common import HealthResponse
from server.app.services.storage_r2 import check_r2_config_ready

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="rag-engine")


@app.on_event("startup")
async def validate_supabase_connection() -> None:
    try:
        async with engine.begin() as conn:
            # Avoid prepared statements (PgBouncer transaction/statement mode incompatibility)
            await conn.execute(sa.text("select 1"))
        logger.info("Supabase DB connection ok")
    except Exception:
        # Do not block startup; just log. Downstream DB ops will still error if DB is unreachable.
        logger.warning("Connect to Supabase database failed (startup check only)", exc_info=True)
    # Check R2 config presence (non-blocking)
    check_r2_config_ready()


# Health
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


# Routers
app.include_router(me.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(conversations.router)
app.include_router(messages.router)
