import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from server.app.db.session import async_session
from server.app.db import models
import sqlalchemy as sa

async def get_latest_failed_job_error():
    async with async_session() as session:
        # Select the latest failed parse job
        stmt = (
            sa.select(models.parse_jobs)
            .where(models.parse_jobs.c.status == 'failed')
            .order_by(models.parse_jobs.c.finished_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.fetchone()
        
        if row:
            job = row._mapping
            print(f"\n--- LATEST FAILED JOB ---")
            print(f"Job ID: {job['id']}")
            print(f"Document ID: {job['document_id']}")
            print(f"Finished At: {job['finished_at']}")
            print(f"ERROR MESSAGE:\n{job['error_message']}")
            print(f"-------------------------\n")
        else:
            print("\nNo failed jobs found in the database.\n")

if __name__ == "__main__":
    try:
        asyncio.run(get_latest_failed_job_error())
    except Exception as e:
        print(f"Error running debug script: {e}")
