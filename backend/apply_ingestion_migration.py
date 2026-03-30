"""
Migration: Add ingestion status tracking columns to missions table.
Run this script once inside the backend container or against the live DB.
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/lhas"
)

MIGRATION_SQL = """
ALTER TABLE missions
    ADD COLUMN IF NOT EXISTS ingestion_status VARCHAR(20) NOT NULL DEFAULT 'idle',
    ADD COLUMN IF NOT EXISTS ingestion_progress INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ingestion_error TEXT,
    ADD COLUMN IF NOT EXISTS ingestion_started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS ingestion_completed_at TIMESTAMP;
"""


async def run():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.exec_driver_sql(MIGRATION_SQL)
    await engine.dispose()
    print("✅ Ingestion status columns added to missions table.")


if __name__ == "__main__":
    asyncio.run(run())
