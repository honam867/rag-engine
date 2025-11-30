import asyncio
import logging
from sqlalchemy import text
from server.app.db.session import engine
from server.app.db.models import metadata

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    logger.info("Creating tables...")
    async with engine.begin() as conn:
        # Enable UUID extension
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        # Create all tables defined in metadata
        await conn.run_sync(metadata.create_all)
    logger.info("Tables created successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())
