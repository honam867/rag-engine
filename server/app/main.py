import asyncio

from fastapi import FastAPI
import sqlalchemy as sa
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from server.app.api.routes import conversations, documents, me, messages, realtime, workspaces
from server.app.core.event_bus import listen_realtime_events
from server.app.core.logging import get_logger, setup_logging
from server.app.db.session import engine
from server.app.schemas.common import HealthResponse
from server.app.services.storage_r2 import check_r2_config_ready

# Load environment variables from .env so that plain os.getenv() calls
# (e.g. OPENAI_API_KEY) see the same config as pydantic Settings.
load_dotenv(".env")

setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="rag-engine")

# Basic CORS for local dev (frontend on 3000). Adjust origins if needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    # Start background listener for cross-process realtime events.
    asyncio.create_task(listen_realtime_events())


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
app.include_router(realtime.router)
